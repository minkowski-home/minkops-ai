"""Shared launch transaction: identity, installed dispatch, pinned inputs, queue."""

from dataclasses import dataclass, field

from jsonschema import ValidationError
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError
from minkops_platform.installation import installed_definition
from minkops_platform.run_controls import resolve_request
from minkops_platform.runtime.assets import config_json

from .application import RESERVED, execution_config, get_handler
from .store import observe, public_run, run_for


@dataclass(frozen=True)
class LaunchInputs:
    """Authorized resources and server-owned domain snapshots from a handler."""

    files: list
    file_ids: list
    catalog_id: object
    selections: dict
    snapshots: dict = field(default_factory=dict)


def launch_run(connection, tenant, user, body, *, task_id=None):
    fingerprint, previous = resolve_request(
        connection,
        tenant["id"],
        body["request_key"],
        body,
        lambda c, tenant_id, request_key: c.execute(
            "SELECT * FROM workflow_runs WHERE tenant_id=%s AND request_key=%s",
            (tenant_id, request_key),
        ).fetchone(),
    )
    if previous:
        return public_run(connection, previous)
    workflow = connection.execute(
        """SELECT * FROM workflows WHERE tenant_id=%s AND key=%s
        AND status='active' FOR SHARE""",
        (tenant["id"], body["key"]),
    ).fetchone()
    if not workflow:
        raise ServiceError("conflict", "This workflow is not active.")
    binding = workflow["execution_binding"]
    if not binding:
        raise ServiceError("invalid", "Install this workflow's execution binding before launching.")
    try:
        if RESERVED.intersection(body["config"]):
            raise ValueError("Run configuration contains reserved runtime fields.")
        definition = installed_definition(binding, body["key"])
        destination = None
        if body.get("destination_device_id"):
            from minkops_platform.desktop import owned_device

            destination = owned_device(connection, tenant["id"], user["id"], body["destination_device_id"])
        handler = get_handler(binding["handler"])
        prepared = handler.prepare_launch(connection, tenant, user, body, workflow, definition)
        files, ids, catalog_id = prepared.files, prepared.file_ids, prepared.catalog_id
        # Only trusted adapters populate this list after tenant-scoped lookup.
        authorized = [
            {"capability": "files.snapshot", "resource_id": str(f["id"]), "sha256": f["sha256"]}
            for f in files
        ]
        config = execution_config(
            definition, prepared.selections, binding=binding, authorized_bindings=authorized
        )
        if prepared.snapshots.keys() & (config.keys() | {"file_provenance"}):
            raise ValueError("Domain snapshots cannot replace runtime or selection fields.")
        config.update(prepared.snapshots)
        if destination:
            # This shared routing field is authenticated independently of workflow
            # schemas. A PC choice does not grant tools, folder access or writes.
            config["destination_device_id"] = str(destination["id"])
        config["file_provenance"] = [
            {"id": str(f["id"]), "path": f["path"], "sha256": f["sha256"]} for f in files
        ]
    except (ValueError, ValidationError) as error:
        raise ServiceError("invalid", str(error).splitlines()[0]) from error
    if task_id:
        task = connection.execute(
            "SELECT id FROM tasks WHERE tenant_id=%s AND id=%s FOR UPDATE", (tenant["id"], task_id)
        ).fetchone()
        if not task:
            raise ServiceError("not_found", "Launch task is not in this workflow's workspace.")
    else:
        summary = getattr(handler, "queued_summary", "Queued for workflow.")
        task = connection.execute(
            """INSERT INTO tasks (tenant_id,workflow_id,title,summary)
            VALUES (%s,%s,%s,%s) RETURNING id""",
            (tenant["id"], workflow["id"], workflow["name"], summary),
        ).fetchone()
    run = connection.execute(
        """INSERT INTO workflow_runs
        (tenant_id,task_id,actor_id,workflow_key,definition_version,request_key,request_hash,config,file_ids,catalog_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            tenant["id"],
            task["id"],
            user["id"],
            body["key"],
            definition.metadata["version"],
            body["request_key"],
            fingerprint,
            config_json(connection, tenant["id"], config),
            Jsonb(ids),
            catalog_id,
        ),
    ).fetchone()
    from .assets import hydrate
    hydrate(connection, run)
    if hasattr(handler, "launched"):
        handler.launched(connection, run)
        run = run_for(connection, tenant["id"], run["id"])
    observe(
        connection, run, "queued", getattr(handler, "queued_summary", "Queued for workflow."), 5
    )
    return public_run(connection, run)
