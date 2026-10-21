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

from minkops_platform.runtime.bundles import SESSIONS_SCHEMA, build_session_bundle

DESCRIPTOR_SCHEMA = {
    "type": "object",
    "required": [
        "key",
        "version",
        "name",
        "description",
        "owner",
        "handler",
        "tenant_config_schema",
        "run_config_schema",
        "instructions",
        "tenant_defaults",
        "run_defaults",
        "sessions",
    ],
    "properties": {
        "key": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
        "owner": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
        "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
        **{
            key: {"type": "string", "minLength": 1}
            for key in ("name", "description", "tenant_config_schema", "run_config_schema", "instructions")
        },
        "tenant_defaults": {"type": "object"},
        "run_defaults": {"type": "object"},
        "sessions": SESSIONS_SCHEMA,
        # The run handler (work.HANDLER_MODULES) and the review surface that presents its records.
        "handler": {"type": "string", "pattern": "^[a-z][a-z0-9.-]*$"},
        "presentation": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
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
    instructions: str
    # The workflow's pinned model and instructions (runtime.bundles).
    session_bundle: dict[str, Any]


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

    schemas = [json.loads(read_local(key)) for key in ("tenant_config_schema", "run_config_schema")]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    instructions = read_local("instructions")
    if not instructions.strip():
        raise ValueError("Workflow instructions must not be empty")
    validate(schemas[0], metadata["tenant_defaults"])
    partial_run_schema = {**schemas[1], "required": []}
    validate(partial_run_schema, metadata["run_defaults"])
    return WorkflowDefinition(metadata, *schemas, instructions, build_session_bundle(directory, metadata))


def resolve_run_config(definition: WorkflowDefinition, tenant_defaults: dict, run_values: dict) -> dict:
    """A detached run configuration: definition defaults, then tenant preferences, then the run's own values.

    Tenant defaults are preferences, not permissions: what a run may read or
    write comes from trusted application state, never from its configuration.
    """
    validate(definition.tenant_schema, tenant_defaults)
    resolved = deepcopy({**definition.metadata["run_defaults"], **tenant_defaults, **run_values})
    validate(definition.run_schema, resolved)
    return resolved


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
                        "handler": metadata["handler"],
                        "presentation": metadata.get("presentation"),
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
