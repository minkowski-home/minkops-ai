"""Default file-snapshot skill handler with structural checks and human review.

This handler produces a reviewed result only. External writes require an adapter
with its own approval/readback contract, never an arbitrary agent instruction.
"""

import json

from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError
from minkops_platform.resources import files_for
from minkops_platform.workflows import resolve_run_config

from .application import enforce_policies
from .launch import LaunchInputs
from .store import observe


class ProposalHandler:
    def public_fields(self, connection, run):
        return {"writes": []}

    executing_summary = "Inspecting the selected workflow inputs."

    def prepare_launch(self, connection, tenant, user, body, workflow, definition):
        ids = list(map(str, body["file_ids"]))
        if len(ids) != len(set(ids)):
            raise ServiceError("invalid", "Select each file only once.")
        if body.get("catalog_id"):
            raise ServiceError("invalid", "This handler does not use Accounts catalogs.")
        files = files_for(connection, tenant["id"], ids)
        if any(not f["current"] for f in files):
            raise ServiceError("conflict", "Refresh changed source files before launching.")
        if len(files) > 45 or sum(len(f["content"]) for f in files) > 8_000_000:
            raise ServiceError("invalid", "Selected inputs exceed the supported run size.")
        sources = {str(f["source_id"]) for f in files}
        selections = {**body["config"]}
        if "source_ids" in definition.run_schema.get("properties", {}):
            selections["source_ids"] = sorted(sources)
        config = resolve_run_config(
            definition,
            workflow["config_values"],
            selections,
            allowed_source_ids=sources,
            allowed_destination_ids=set(),
        )
        return LaunchInputs(files, ids, None, config)

    def prepare(self, connection, run):
        files = files_for(connection, run["tenant_id"], run["file_ids"])
        context = {
            "config": run["config"],
            "definition_version": run["definition_version"],
            "files": [{"id": str(f["id"]), "path": f["path"]} for f in files],
        }
        return files, context, {}

    def validate(self, run, files, context, domain, result):
        snapshot = run["config"]["execution_snapshot"]
        descriptor = json.loads(snapshot["files"]["workflow.json"])
        schema = json.loads(snapshot["files"][descriptor["output_schema"]])
        Draft202012Validator(schema).validate(result)
        return result

    def finish(self, connection, store, run, context, domain, result):
        store.observe(connection, run, "review", "Review the workflow result.", 70)

    def approve(self, connection, tenant, user, run, body):
        # Policy annotations are application-owned, outside the declared model
        # result contract. Recompute them after validating the reviewed payload.
        reviewed = {key: value for key, value in body["result"].items() if key != "requires_review"}
        result = self.validate(run, [], {}, {}, reviewed)
        result = enforce_policies(run["config"], result)
        connection.execute(
            """UPDATE workflow_runs SET result=%s,review_actor_id=%s,reviewed_at=now()
            WHERE tenant_id=%s AND id=%s""",
            (Jsonb(result), user["id"], tenant["id"], run["id"]),
        )
        observe(connection, run, "completed", "Workflow result reviewed.", 100)
