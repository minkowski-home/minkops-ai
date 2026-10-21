"""Tenant-scoped durable storage for installed workflows."""

from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError
from minkops_platform.run_controls import control_state, observe_task


class WorkflowRunStore:
    def candidates(self, connection):
        return connection.execute("""SELECT id,tenant_id,task_id FROM workflow_runs WHERE
            NOT is_batch AND NOT superseded
            AND EXISTS (SELECT 1 FROM tasks t WHERE t.tenant_id=workflow_runs.tenant_id AND t.id=workflow_runs.task_id AND t.control_state='active')
            AND (state='queued' OR (state='executing' AND updated_at < now()-interval '30 seconds'))
            AND (context_job_id IS NULL OR EXISTS
                (SELECT 1 FROM desktop_jobs j WHERE j.tenant_id=workflow_runs.tenant_id
                 AND j.id::text=context_job_id AND j.state IN ('completed','failed')))
            -- A session waiting for a client profile starts once that profile is active.
            AND NOT blocked
            ORDER BY updated_at LIMIT 10""").fetchall()

    def get(self, connection, tenant_id, run_id):
        return run_for(connection, tenant_id, run_id)

    def fail(self, connection, run, message):
        connection.execute(
            "UPDATE workflow_runs SET error=%s WHERE tenant_id=%s AND id=%s",
            (message, run["tenant_id"], run["id"]),
        )
        self.observe(connection, run, "failed", message, 20)

    def save_session(self, connection, run, session_id, turn_id):
        connection.execute(
            """UPDATE workflow_runs SET session_id=coalesce(%s,session_id),
                turn_id=coalesce(%s,turn_id),updated_at=now() WHERE tenant_id=%s AND id=%s""",
            (session_id, turn_id, run["tenant_id"], run["id"]),
        )

    def save_result(self, connection, run, result):
        connection.execute(
            "UPDATE workflow_runs SET result=%s WHERE tenant_id=%s AND id=%s",
            (Jsonb(result), run["tenant_id"], run["id"]),
        )

    def claim_cleanup(self, connection):
        run = connection.execute("""SELECT id,tenant_id,session_id FROM workflow_runs
            WHERE state NOT IN ('queued','executing') AND session_id IS NOT NULL
            AND NOT session_closed AND cleanup_attempt_count < 10
            AND coalesce(cleanup_attempt_at,'epoch') < now()-interval '1 minute'
            ORDER BY updated_at LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED""").fetchone()
        if run:
            connection.execute(
                """UPDATE workflow_runs SET config=config || jsonb_build_object('cleanup_attempt_at',now(),
                    'cleanup_attempt_count',coalesce((config->>'cleanup_attempt_count')::integer,0)+1)
                    WHERE tenant_id=%s AND id=%s""",
                (run["tenant_id"], run["id"]),
            )
        return run

    def mark_closed(self, connection, run):
        connection.execute(
            """UPDATE workflow_runs SET config=config || '{"hosted_session_closed":true}'::jsonb
                WHERE tenant_id=%s AND id=%s""",
            (run["tenant_id"], run["id"]),
        )

    def observe(self, connection, run, state, summary, progress):
        observe(connection, run, state, summary, progress)


def run_for(connection, tenant_id, run_id, lock=False, *, hydrate_assets=True):
    row = connection.execute(
        "SELECT * FROM workflow_runs WHERE tenant_id=%s AND id=%s"
        # Run identities never change. This still serializes business mutations
        # while permitting the separate diagnostic transaction's FK key check.
        + (" FOR NO KEY UPDATE" if lock else ""),
        (tenant_id, run_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Run not found.")
    if hydrate_assets:
        from .assets import hydrate
        hydrate(connection, row)
    return row


def observe(connection, run, state, summary, progress):
    if control_state(connection, run["tenant_id"], run["task_id"]) == "stopped":
        return
    connection.execute(
        "UPDATE workflow_runs SET state=%s,updated_at=now() WHERE tenant_id=%s AND id=%s",
        (state, run["tenant_id"], run["id"]),
    )
    # Child sessions update their own durable state. Only their orchestrator
    # publishes the aggregate task, so one child cannot complete its siblings.
    if run.get("parent_run_id"):
        return
    if state == "failed":
        from minkops_platform.attention import audit, record
        item = record(connection, run, f"run:{run['id']}", run.get("workflow_key", "Workflow"), "Needs attention")
        audit(connection, item, None, "failed", summary)
    observe_task(
        connection,
        tenant_id=run["tenant_id"],
        task_id=run["task_id"],
        run_id=run["id"],
        state=state,
        summary=summary,
        progress=progress,
        event_prefix="account_run",
    )


def public_run(connection, run):
    from .application import binding_for, get_handler

    keys = ("id", "tenant_id", "task_id", "actor_id", "workflow_key", "definition_version",
            "state", "file_ids", "catalog_id", "parent_run_id", "result", "error", "created_at", "updated_at")
    value = {key: run.get(key) for key in keys}
    config = run["config"]
    value["config"] = {key: config[key] for key in ("file_provenance", "destination_device_id", "output_mode", "review_mode") if key in config}
    if config.get("tally_target"):
        target = config["tally_target"]
        value["config"]["tally_target"] = {key: target[key] for key in ("company", "company_mode", "locked_company_guid", "device_id", "discovery_id") if key in target}
        value["config"]["tally_target"]["companies"] = [
            {key: company[key] for key in ("company", "voucher_type_error", "books_from", "period_to") if key in company}
            | {"references": {"company_guid": company.get("references", {}).get("company_guid")},
               "voucher_type": {"NAME": company.get("voucher_type", {}).get("NAME")}}
            for company in target.get("companies", [])]
    # Legacy proposals have no persisted presentation controls. New validated
    # results pin those once, so repeated status reads never load their assets.
    if run["state"] == "review" and (run.get("result") or {}).get("records") \
            and not run["result"].get("_decision_projection"):
        from .assets import hydrate
        hydrate(connection, run)
    handler = get_handler(binding_for(run).handler)
    control = control_state(connection, run["tenant_id"], run["task_id"])
    presentation = {**run, "state": control} if control != "active" else run
    value.update(handler.public_fields(connection, presentation))
    if config.get("batch") and run["state"] in ("queued", "executing"):
        # A sibling's validated output is useful before the batch completes.
        # These records are display-only: decisions remain fenced by run state.
        children = connection.execute("""SELECT file_ids,state,result,error FROM workflow_runs
            WHERE tenant_id=%s AND parent_run_id=%s AND execution_stage IS NULL
              AND NOT superseded AND state IN ('review','failed') ORDER BY file_ids->>0""",
            (run["tenant_id"], run["id"])).fetchall()
        partial = {"records": [], "unresolved": [], "findings": [], "partial": True}
        from copy import deepcopy
        for child in children:
            if child["state"] == "failed":
                partial["unresolved"].append({"source_file_id": child["file_ids"][0], "code": "extraction_failed",
                                               "reason": "This bill needs an explicit recheck.", "allowed_actions": []})
            else:
                proposal = deepcopy(child["result"] or {})
                for record in proposal.get("records", []):
                    record.update(allowed_actions=[], bulk_actions={})
                partial["records"].extend(proposal.get("records", []))
                partial["unresolved"].extend({**issue, "allowed_actions": []} for issue in proposal.get("unresolved", []))
        value["result"] = partial
    value["control_state"] = control
    if value["control_state"] != "active":
        value["state"] = value["control_state"]
    from .status import execution_status
    value.update(execution_status(connection, run, value["control_state"]))
    if isinstance(value.get("result"), dict):
        value["result"].pop("_decision_projection", None)
    return value
