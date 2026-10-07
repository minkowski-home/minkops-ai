"""Versioned workflow contracts, run configuration, and tenant registration.

This module does not start agents or authorize connections. Callers provide
resource IDs already authorized for the tenant and actor.
"""

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from minkops_platform.runtime.bundles import EXECUTION_SCHEMA, build_snapshot

DESCRIPTOR_SCHEMA = {
    "type": "object",
    "required": [
        "key",
        "version",
        "name",
        "description",
        "owner",
        "tenant_config_schema",
        "run_config_schema",
        "output_schema",
        "instructions",
        "tenant_defaults",
        "run_defaults",
    ],
    "properties": {
        "key": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
        "owner": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
        "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
        **{
            key: {"type": "string", "minLength": 1}
            for key in (
                "name",
                "description",
                "tenant_config_schema",
                "run_config_schema",
                "output_schema",
                "instructions",
            )
        },
        "tenant_defaults": {"type": "object"},
        "run_defaults": {"type": "object"},
        "agent_output_schema": {"type": "string", "minLength": 1},
        "execution": EXECUTION_SCHEMA,
        "handler": {"type": "string", "pattern": "^[a-z][a-z0-9.-]*$"},
        "presentation": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
        "capabilities": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": False,
}


def validate(schema: dict, values: dict) -> None:
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(values)


@dataclass(frozen=True)
class WorkflowDefinition:
    metadata: dict[str, Any]
    tenant_schema: dict[str, Any]
    run_schema: dict[str, Any]
    output_schema: dict[str, Any]
    instructions: str
    agent_output_schema: dict[str, Any] | None = None
    execution_snapshot: dict[str, Any] | None = None


def load_definition(directory: Path) -> WorkflowDefinition:
    """Read one explicit definition directory; never scan customer file sources."""
    directory = directory.resolve()
    metadata = json.loads((directory / "workflow.json").read_text())
    validate(DESCRIPTOR_SCHEMA, metadata)
    if directory.name != metadata["key"]:
        raise ValueError("Workflow directory must match its key")

    def read_local(key: str) -> str:
        path = (directory / metadata[key]).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Definition files must stay inside the workflow directory")
        return path.read_text()

    schemas = [
        json.loads(read_local(key))
        for key in ("tenant_config_schema", "run_config_schema", "output_schema")
    ]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    instructions = read_local("instructions")
    if not instructions.strip():
        raise ValueError("Workflow instructions must not be empty")
    validate(schemas[0], metadata["tenant_defaults"])
    partial_run_schema = {**schemas[1], "required": []}
    validate(partial_run_schema, metadata["run_defaults"])
    agent_schema = (
        json.loads(read_local("agent_output_schema")) if "agent_output_schema" in metadata else None
    )
    if agent_schema is not None:
        Draft202012Validator.check_schema(agent_schema)
    snapshot = build_snapshot(directory, metadata) if "execution" in metadata else None
    return WorkflowDefinition(metadata, *schemas, instructions, agent_schema, snapshot)


def resolve_run_config(
    definition: WorkflowDefinition,
    tenant_defaults: dict,
    run_values: dict,
    *,
    allowed_source_ids: set[str],
    allowed_destination_ids: set[str],
    require_review: bool = False,
) -> dict:
    """Return a detached snapshot after schema and caller-supplied policy checks.

    Tenant defaults are preferences, not permissions. Resource authorization
    must come from trusted application state, never from the run request.
    Persist this snapshot and definition version before eventual execution.
    """
    validate(definition.tenant_schema, tenant_defaults)
    resolved = deepcopy({**definition.metadata["run_defaults"], **tenant_defaults, **run_values})
    validate(definition.run_schema, resolved)
    if not set(resolved.get("source_ids", [])).issubset(allowed_source_ids):
        raise ValueError("Run selects a source outside the authorized scope")
    destination = resolved.get("destination_id")
    if destination is not None and destination not in allowed_destination_ids:
        raise ValueError("Run selects an unauthorized destination")
    if require_review and resolved.get("review_mode") != "all_outputs":
        raise ValueError("This run requires review of all outputs")
    return resolved


def validate_output(
    definition: WorkflowDefinition,
    result: dict,
    *,
    run_config: dict,
    confirmed_schema: dict,
) -> None:
    """Validate bill-entry's envelope and each record's discovered business data.

    The caller loads confirmed_schema from authorized catalog storage, never
    from agent output. It contains catalog_version, schema_id, schema_version,
    and the confirmed JSON Schema under `schema`. Its snapshot must be pinned
    to the run. This validates structure, not reconciliation or write approval.
    """
    if definition.metadata["key"] != "bill-entry":
        raise ValueError("Record schema validation applies to bill-entry")
    validate(definition.run_schema, run_config)
    validate(definition.output_schema, result)
    for key in ("catalog_version", "schema_id", "schema_version"):
        if confirmed_schema.get(key) != run_config[key] or result[key] != run_config[key]:
            raise ValueError(f"Result and confirmed schema must match the run's {key}")
    schema = confirmed_schema["schema"]
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("Confirmed business schema must describe an object")

    def check_references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                    not isinstance(child, str) or not child.startswith("#")
                ):
                    raise ValueError("Business schemas cannot load external references")
                check_references(child)
        elif isinstance(value, list):
            for child in value:
                check_references(child)

    check_references(schema)
    Draft202012Validator.check_schema(schema)
    for record in result["records"]:
        validate(schema, record["data"])


def register_workflow(
    connection, tenant_id, definition: WorkflowDefinition, initial_defaults: dict | None = None
):
    """Register a planned tenant workflow without replacing existing settings.

    Validate existing settings against the new schema before updating metadata.
    The caller must authorize tenant administration before calling this function.
    Works inside the caller's transaction; no independent commit occurs.
    """
    metadata = definition.metadata
    defaults = deepcopy(
        metadata["tenant_defaults"] if initial_defaults is None else initial_defaults
    )
    validate(definition.tenant_schema, defaults)
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        owner = cursor.execute(
            "SELECT id FROM employees WHERE tenant_id = %s AND key = %s",
            (tenant_id, metadata["owner"]),
        ).fetchone()
        if not owner:
            raise ValueError("Workflow owner must be registered in this tenant first")
        # Serialize registrations for the same tenant/key, including first install.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{tenant_id}:{metadata['key']}",),
        )
        existing = cursor.execute(
            "SELECT id, config_values FROM workflows WHERE tenant_id = %s AND key = %s FOR UPDATE",
            (tenant_id, metadata["key"]),
        ).fetchone()
        if existing:
            validate(definition.tenant_schema, existing[1])
        workflow_id = cursor.execute(
            """INSERT INTO workflows
               (tenant_id, key, name, description, status, config_schema, config_values, execution_binding)
               VALUES (%s, %s, %s, %s, 'planned', %s, %s, %s)
               ON CONFLICT (tenant_id, key) DO UPDATE SET
                 name = EXCLUDED.name, description = EXCLUDED.description,
                 config_version = workflows.config_version +
                   CASE WHEN workflows.config_schema IS DISTINCT FROM EXCLUDED.config_schema
                        THEN 1 ELSE 0 END,
                 config_schema = EXCLUDED.config_schema,
                 execution_binding = coalesce(workflows.execution_binding, EXCLUDED.execution_binding)
               RETURNING id""",
            (
                tenant_id,
                metadata["key"],
                metadata["name"],
                metadata["description"],
                Jsonb(definition.tenant_schema),
                Jsonb(defaults),
                Jsonb(
                    {
                        "definition": f"{metadata['owner']}/workflows/{metadata['key']}",
                        "handler": metadata.get("handler", "skill.proposal"),
                        "presentation": metadata.get("presentation", "proposal"),
                        "policies": [],
                        "capabilities": metadata.get("capabilities", []),
                    }
                ),
            ),
        ).fetchone()[0]
        cursor.execute(
            """INSERT INTO workflow_employees (tenant_id, workflow_id, employee_id)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (tenant_id, workflow_id, owner[0]),
        )
    return workflow_id
