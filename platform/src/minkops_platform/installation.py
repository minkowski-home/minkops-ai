"""Validated repository composition and atomic tenant installation.

CLI and future admin transports share these services. Installation changes no
identity/membership, grants no file/tool access, and preserves operator settings.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb

from .errors import ServiceError
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
                    "policies": {"type": "array"},
                },
            },
        }
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


def load_solution(root: Path, solution_id: str) -> Installation:
    from .runtime.application import get_handler, validate_policies

    solution = owned_directory(root / "solutions", solution_id)
    manifest = read_json(solution / "installation.json")
    validate(
        {
            "type": "object",
            "required": ["tenant", "employees"],
            "properties": {
                "tenant": {"type": "string", "pattern": SLUG.pattern},
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
    employees, workflows, bindings = [], {}, {}
    for employee_key in manifest["employees"]:
        directory = owned_directory(root / "employees", employee_key)
        metadata = read_json(directory / "employee.json")
        validate(EMPLOYEE_SCHEMA, metadata)
        if metadata["key"] != employee_key:
            raise ValueError("Employee directory must match its key.")
        Draft202012Validator.check_schema(metadata["config_schema"])
        validate(metadata["config_schema"], metadata["defaults"])
        employees.append(EmployeeDefinition(metadata))
        client_employee = owned_directory(solution / "employees", employee_key)
        binding = read_json(client_employee / "binding.json")
        validate(BINDING_SCHEMA, binding)
        for item in binding["workflows"]:
            key = item["key"]
            if key in workflows:
                raise ValueError("Workflow keys must be unique in a tenant.")
            definition = load_definition(owned_directory(directory / "workflows", key))
            from .solution_policy import bind_definition

            definition = bind_definition(definition, solution_id, repository_root=root)
            if definition.metadata["owner"] != employee_key:
                raise ValueError("Workflow must belong to its declared employee.")
            handler = definition.metadata.get("handler", "skill.proposal")
            get_handler(handler)
            policies = item.get("policies", [])
            validate_policies(policies)
            validate(
                definition.tenant_schema,
                item.get("defaults", definition.metadata["tenant_defaults"]),
            )
            workflows[key] = definition
            bindings[key] = {
                **item,
                "definition": f"{employee_key}/workflows/{key}",
                "handler": handler,
                "presentation": definition.metadata.get("presentation", "proposal"),
                "capabilities": definition.metadata.get("capabilities", []),
                "policies": policies,
            }
    return Installation(manifest["tenant"], employees, workflows, bindings)


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
            binding = {
                k: spec[k]
                for k in ("definition", "handler", "presentation", "policies", "capabilities")
            }
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
        return installed
