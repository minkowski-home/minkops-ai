"""Validated repository composition and atomic tenant installation.

CLI and future admin transports share these services. Installation changes no
identity/membership, grants no file/tool access, and preserves operator settings.
"""

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb

from .errors import ServiceError
from .resources import REPOSITORY_ROOT
from .workflows import load_definition, register_workflow, validate

SLUG = re.compile(r"^[a-z][a-z0-9-]*$")
EMPLOYEE_SCHEMA = {
    "type": "object",
    "required": ["key", "name", "description", "config_schema", "defaults"],
    "properties": {
        "key": {"type": "string", "pattern": SLUG.pattern},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "config_schema": {"type": "object"},
        "defaults": {"type": "object"},
    },
    "additionalProperties": False,
}
BINDING_SCHEMA = {
    "type": "object",
    "required": ["workflows"],
    "additionalProperties": False,
    "properties": {
        "employee": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "defaults": {"type": "object"},
            },
        },
        "workflows": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key"],
                "additionalProperties": False,
                "properties": {
                    "key": {"type": "string", "pattern": SLUG.pattern},
                    "status": {"enum": ["active", "paused", "planned"]},
                    "defaults": {"type": "object"},
                    "variant": {"type": "string", "minLength": 1},
                },
            },
        },
        # Rules the client agreed, seeded once into the employee's memory for the solution's client business.
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "text"],
                "additionalProperties": False,
                "properties": {
                    "key": {"type": "string", "pattern": SLUG.pattern},
                    "workflow": {"type": "string", "pattern": SLUG.pattern},
                    "text": {"type": "string", "minLength": 1, "maxLength": 2000},
                },
            },
        },
    },
}


def owned_directory(root: Path, key: str) -> Path:
    if not isinstance(key, str) or not SLUG.fullmatch(key):
        raise ValueError("Definition identity must be a lowercase slug.")
    directory = root / key
    if directory.is_symlink() or not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("Definitions must stay inside their repository layer.")
    return directory


def read_json(path):
    if path.is_symlink():
        raise ValueError("Definition files cannot follow symlinks.")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class EmployeeDefinition:
    metadata: dict


@dataclass(frozen=True)
class Installation:
    tenant_slug: str
    employees: list
    workflows: dict
    bindings: dict
    # The solution's own client business in the tenant, and each employee's rules to seed for it.
    client: dict | None = None
    rules: dict = field(default_factory=dict)


def client_variant(definition, directory, filename, solution_id):
    """Add a client's procedure to a core workflow's instructions; never replace its contracts.

    Client procedures are trusted repository content, but permission and
    approval enforcement stays in the run's handler. Both versions and the
    exact composed instructions are pinned with each run's bundle.
    """
    from .runtime.bundles import read_resource

    variant = json.loads(read_resource(directory, filename))
    validate(
        {
            "type": "object",
            "required": ["version"],
            "additionalProperties": False,
            "properties": {
                "version": {"type": "string", "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$"},
                "instructions": {"type": "string", "minLength": 1},
                "defaults": {"type": "object"},
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
            },
        },
        variant,
    )
    metadata = deepcopy(definition.metadata)
    metadata["tenant_defaults"] = {**metadata["tenant_defaults"], **variant.get("defaults", {})}
    validate(definition.tenant_schema, metadata["tenant_defaults"])
    for key in ("name", "description"):
        if key in variant:
            metadata[key] = variant[key]
    bundle = deepcopy(definition.session_bundle)
    bundle["variant"] = {"solution": solution_id, "core_version": metadata["version"], "version": variant["version"]}
    instructions = definition.instructions
    if variant.get("instructions"):
        addition = read_resource(directory, variant["instructions"])
        if not addition.strip():
            raise ValueError("Client instructions must not be empty.")
        bundle["instructions"] += "\n\n## Client procedure\n\n" + addition.strip()
        instructions += "\n\n## Client procedure\n\n" + addition
    return replace(definition, metadata=metadata, instructions=instructions, session_bundle=bundle)


def load_solution(root: Path, solution_id: str) -> Installation:
    from .work import HANDLER_MODULES

    solution = owned_directory(root / "solutions", solution_id)
    manifest = read_json(solution / "installation.json")
    validate(
        {
            "type": "object",
            "required": ["tenant", "employees"],
            "properties": {
                "tenant": {"type": "string", "pattern": SLUG.pattern},
                "client": {
                    "type": "object",
                    "required": ["slug", "name"],
                    "additionalProperties": False,
                    "properties": {
                        "slug": {"type": "string", "pattern": SLUG.pattern},
                        "name": {"type": "string", "minLength": 1, "maxLength": 200},
                    },
                },
                "employees": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": SLUG.pattern},
                },
            },
            "additionalProperties": False,
        },
        manifest,
    )
    employees, workflows, bindings, rules = [], {}, {}, {}
    for employee_key in manifest["employees"]:
        directory = owned_directory(root / "employees", employee_key)
        metadata = read_json(directory / "employee.json")
        validate(EMPLOYEE_SCHEMA, metadata)
        if metadata["key"] != employee_key:
            raise ValueError("Employee directory must match its key.")
        Draft202012Validator.check_schema(metadata["config_schema"])
        validate(metadata["config_schema"], metadata["defaults"])
        client_employee = owned_directory(solution / "employees", employee_key)
        binding = read_json(client_employee / "binding.json")
        validate(BINDING_SCHEMA, binding)
        metadata = {
            **metadata,
            **binding.get("employee", {}),
            "defaults": {
                **metadata["defaults"],
                **binding.get("employee", {}).get("defaults", {}),
            },
        }
        validate(metadata["config_schema"], metadata["defaults"])
        employees.append(EmployeeDefinition(metadata))
        for item in binding["workflows"]:
            key = item["key"]
            if key in workflows:
                raise ValueError("Workflow keys must be unique in a tenant.")
            definition = load_definition(owned_directory(directory / "workflows", key))
            if item.get("variant"):
                variant_directory = owned_directory(client_employee / "workflows", key)
                definition = client_variant(
                    definition, variant_directory, item["variant"], solution_id
                )
            if definition.metadata["owner"] != employee_key:
                raise ValueError("Workflow must belong to its declared employee.")
            handler = definition.metadata["handler"]
            if handler not in HANDLER_MODULES:
                raise ValueError(f"Workflow {key} names an unknown handler.")
            defaults = {**definition.metadata["tenant_defaults"], **item.get("defaults", {})}
            validate(definition.tenant_schema, defaults)
            workflows[key] = definition
            bindings[key] = {
                **item,
                "defaults": defaults,
                "solution": solution_id,
                "definition": f"{employee_key}/workflows/{key}",
                "handler": handler,
                "presentation": definition.metadata.get("presentation"),
            }
        if binding.get("rules"):
            if "client" not in manifest:
                raise ValueError("Seeded rules need the solution's client business in installation.json.")
            known = {item["key"] for item in binding["workflows"]}
            if any(rule.get("workflow") not in (None, *known) for rule in binding["rules"]):
                raise ValueError("A seeded rule must name one of its employee's workflows.")
            rules[employee_key] = binding["rules"]
    return Installation(manifest["tenant"], employees, workflows, bindings, manifest.get("client"), rules)


def register_employee(connection, tenant_id, definition):
    metadata = definition.metadata
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"employee:{tenant_id}:{metadata['key']}",),
        )
        existing = cursor.execute(
            "SELECT config_values FROM employees WHERE tenant_id=%s AND key=%s FOR UPDATE",
            (tenant_id, metadata["key"]),
        ).fetchone()
        validate(metadata["config_schema"], existing[0] if existing else metadata["defaults"])
        return cursor.execute(
            """INSERT INTO employees (tenant_id,key,name,description,config_schema,config_values)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,key) DO UPDATE SET
            name=EXCLUDED.name,description=EXCLUDED.description,
            config_version=employees.config_version + CASE WHEN employees.config_schema IS DISTINCT FROM
                EXCLUDED.config_schema THEN 1 ELSE 0 END,config_schema=EXCLUDED.config_schema RETURNING id""",
            (
                tenant_id,
                metadata["key"],
                metadata["name"],
                metadata["description"],
                Jsonb(metadata["config_schema"]),
                Jsonb(metadata["defaults"]),
            ),
        ).fetchone()[0]


def install(connection, installation: Installation, *, actor_email: str):
    """Authorize installation, then apply the entire composition in one transaction."""
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        tenant = cursor.execute(
            "SELECT * FROM tenants WHERE slug=%s FOR UPDATE", (installation.tenant_slug,)
        ).fetchone()
        if not tenant:
            raise ServiceError("not_found", "Create the tenant through normal provisioning first.")
        actor = cursor.execute(
            """SELECT u.id,u.is_platform_admin,m.role FROM users u
            LEFT JOIN memberships m ON m.user_id=u.id AND m.tenant_id=%s
            WHERE lower(u.email)=lower(%s) AND u.email_verified_at IS NOT NULL""",
            (tenant["id"], actor_email),
        ).fetchone()
        if not actor or not (actor["is_platform_admin"] or actor["role"] == "admin"):
            raise ServiceError(
                "forbidden", "Installation requires a verified tenant or platform administrator."
            )
        for employee in installation.employees:
            register_employee(connection, tenant["id"], employee)
        installed = []
        for key, definition in installation.workflows.items():
            spec = installation.bindings[key]
            existing = cursor.execute(
                "SELECT id FROM workflows WHERE tenant_id=%s AND key=%s", (tenant["id"], key)
            ).fetchone()
            workflow_id = register_workflow(
                connection, tenant["id"], definition, spec.get("defaults")
            )
            binding = {k: spec[k] for k in ("definition", "handler", "presentation", "solution")}
            cursor.execute(
                "UPDATE workflows SET execution_binding=%s WHERE tenant_id=%s AND id=%s",
                (Jsonb(binding), tenant["id"], workflow_id),
            )
            if not existing:
                cursor.execute(
                    "UPDATE workflows SET status=%s WHERE tenant_id=%s AND id=%s",
                    (spec.get("status", "planned"), tenant["id"], workflow_id),
                )
            cursor.execute(
                """INSERT INTO event_outbox (tenant_id,event_type,aggregate_id,payload)
                VALUES (%s,'workflow.installed',%s,%s)""",
                (
                    tenant["id"],
                    workflow_id,
                    Jsonb(
                        {
                            "actor_id": str(actor["id"]),
                            "key": key,
                            "definition_version": definition.metadata["version"],
                        }
                    ),
                ),
            )
            installed.append(key)
        if installation.client:
            from . import clients
            from .accounts import memory

            # Both run on this installation's dict-row cursor, whatever the caller's connection returns.
            client = clients.ensure(cursor, tenant, installation.client["slug"], installation.client["name"])
            for employee_key, seeds in installation.rules.items():
                memory.seed(cursor, tenant["id"], client["id"], seeds, employee=employee_key)
        return installed


def installed_definition(binding, key):
    """Resolve only a trusted installation's employee-owned path."""
    relative = binding["definition"]
    parts = PurePosixPath(relative).parts
    if len(parts) != 3 or parts[1] != "workflows" or parts[2] != key or "\\" in relative:
        raise ValueError("Installed workflow definition has an invalid path.")
    root = REPOSITORY_ROOT / "employees"
    directory = root / relative
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("Installed workflow definition must stay inside employees.")
    definition = load_definition(directory)
    if binding.get("solution"):
        composition = load_solution(REPOSITORY_ROOT, binding["solution"])
        if key not in composition.workflows or composition.bindings[key]["definition"] != relative:
            raise ValueError("Installed client variant differs from its composition. Reinstall explicitly.")
        definition = composition.workflows[key]
    if (
        definition.metadata["owner"] != parts[0]
        or definition.metadata["handler"] != binding["handler"]
        or definition.metadata.get("presentation") != binding.get("presentation")
    ):
        raise ValueError(
            "Installed workflow binding differs from its definition. Reinstall explicitly."
        )
    return definition


def installed(connection, tenant_id, key):
    """An active workflow of the tenant and its definition, exactly as its installation binds it."""
    workflow = connection.execute("SELECT * FROM workflows WHERE tenant_id=%s AND key=%s AND status='active'",
                                  (tenant_id, key)).fetchone()
    if not workflow or not workflow["execution_binding"]:
        raise ServiceError("conflict", "This workflow is not active.")
    try:
        return workflow, installed_definition(workflow["execution_binding"], key)
    except ValueError as error:
        raise ServiceError("conflict", str(error)) from error
