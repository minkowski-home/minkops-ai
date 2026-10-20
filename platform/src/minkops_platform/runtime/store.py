"""Tenant-scoped durable storage for installed workflows."""

from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError
from minkops_platform.run_controls import control_state, observe_task


class WorkflowRunStore:
    def candidates(self, connection):
        return connection.execute("""SELECT * FROM workflow_runs WHERE
            NOT coalesce((config->>'batch')::boolean,false)
            AND EXISTS (SELECT 1 FROM tasks t WHERE t.tenant_id=workflow_runs.tenant_id AND t.id=workflow_runs.task_id AND t.control_state='active')
            AND (state='queued' OR (state='executing' AND updated_at < now()-interval '30 seconds'))
            AND (NOT config ? 'tally_context_job_id' OR EXISTS
                (SELECT 1 FROM desktop_jobs j WHERE j.tenant_id=workflow_runs.tenant_id
                 AND j.id::text=config->>'tally_context_job_id' AND j.state IN ('completed','failed')))
            -- A session waiting for a client profile starts once that profile is active.
            AND NOT config ? 'awaits'
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
            AND NOT coalesce((config->>'hosted_session_closed')::boolean,false)
            AND coalesce((config->>'cleanup_attempt_count')::integer,0) < 10
            AND coalesce((config->>'cleanup_attempt_at')::timestamptz,'epoch') < now()-interval '1 minute'
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


def run_for(connection, tenant_id, run_id, lock=False):
    row = connection.execute(
        "SELECT * FROM workflow_runs WHERE tenant_id=%s AND id=%s"
        # Run identities never change. This still serializes business mutations
        # while permitting the separate diagnostic transaction's FK key check.
        + (" FOR NO KEY UPDATE" if lock else ""),
        (tenant_id, run_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Run not found.")
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

    value = {key: data for key, data in run.items() if key != "request_hash"}
    handler = get_handler(binding_for(run).handler)
    value.update(handler.public_fields(connection, run))
    value["control_state"] = control_state(connection, run["tenant_id"], run["task_id"])
    if value["control_state"] != "active":
        value["state"] = value["control_state"]
    return value
