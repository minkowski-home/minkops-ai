"""Shared request identity and task observations; callers own transactions."""

import hashlib
import json

from psycopg.types.json import Jsonb

from .errors import ServiceError

TASK_STATUS = {
    "queued": "running",
    "executing": "running",
    "review": "attention",
    "approved": "running",
    "writing": "handoff",
    "completed": "completed",
    "failed": "failed",
}


def control_state(connection, tenant_id, task_id):
    row = connection.execute("SELECT control_state FROM tasks WHERE tenant_id=%s AND id=%s",
                             (tenant_id, task_id)).fetchone()
    return row["control_state"] if row else "active"


def require_active(connection, tenant_id, task_id):
    """Fence new operations; receipts for work already underway bypass this gate."""
    state = control_state(connection, tenant_id, task_id)
    if state != "active":
        raise ServiceError("conflict", f"This task is {state}." + (" Resume it to continue." if state == "paused" else " Start a new run to continue."))


def owns_task(connection, tenant_id, task_id, actor_id):
    owners = connection.execute("""SELECT actor_id FROM workflow_runs WHERE tenant_id=%s AND task_id=%s
        UNION SELECT actor_id FROM discovery_runs WHERE tenant_id=%s AND task_id=%s
        UNION SELECT actor_id FROM desktop_jobs WHERE tenant_id=%s AND task_id=%s AND operation NOT LIKE 'attention.%%'""",
        (tenant_id, task_id, tenant_id, task_id, tenant_id, task_id)).fetchall()
    return bool(owners) and all(str(row["actor_id"]) == str(actor_id) for row in owners)


def task_control(connection, tenant_id, user, task_id, action):
    """Persist operator intent separately from execution facts, without undoing saves.

    Lock runs before tasks, matching write approval and receipt reconciliation.
    A pause lets an underway operation finish; dispatch and approvals are fenced.
    Stop is irreversible and cancels unsaved plans while accepting late receipts.
    """
    if action not in ("pause", "resume", "stop"):
        raise ServiceError("invalid", "Choose pause, resume or stop.")
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"control:{task_id}",))
    runs = connection.execute("SELECT * FROM workflow_runs WHERE tenant_id=%s AND task_id=%s ORDER BY id FOR UPDATE",
                              (tenant_id, task_id)).fetchall()
    task = connection.execute("SELECT * FROM tasks WHERE tenant_id=%s AND id=%s FOR UPDATE", (tenant_id, task_id)).fetchone()
    if not task:
        raise ServiceError("not_found", "Task not found.")
    if not owns_task(connection, tenant_id, task_id, user["id"]):
        raise ServiceError("forbidden", "Only the operator who started this task can control it.")
    target = {"pause": "paused", "resume": "active", "stop": "stopped"}[action]
    if task["control_state"] == target:
        return task
    if task["control_state"] == "stopped" or (task["control_state"] == "active" and task["status"] in ("completed", "failed")):
        raise ServiceError("conflict", "This task has ended. Start a new run to continue.")
    if action == "stop":
        # Skip an already claimed job rather than waiting in the inverse
        # job -> run lock order. It is an underway operation, not queued work.
        connection.execute("""WITH queued AS (SELECT id FROM desktop_jobs WHERE tenant_id=%s AND task_id=%s
            AND state='queued' AND operation<>'attention.refresh' FOR UPDATE SKIP LOCKED)
            UPDATE desktop_jobs j SET state='failed',error='Stopped by operator.',updated_at=now()
            FROM queued WHERE j.id=queued.id""", (tenant_id, task_id))
        for run in runs:
            connection.execute("UPDATE workflow_runs SET state='failed',error='Stopped by operator.',updated_at=now() WHERE tenant_id=%s AND id=%s AND state NOT IN ('completed','failed')",
                               (tenant_id, run["id"]))
            connection.execute("UPDATE account_writes SET cancelled_at=coalesce(cancelled_at,now()) WHERE tenant_id=%s AND run_id=%s AND verified_at IS NULL", (tenant_id, run["id"]))
            connection.execute("UPDATE account_tally_writes SET cancelled_at=coalesce(cancelled_at,now()) WHERE tenant_id=%s AND run_id=%s AND finished_at IS NULL", (tenant_id, run["id"]))
            binding = run["config"].get("runtime_binding", {})
            # A batch parent owns its bills' attention; its children would
            # otherwise open a second item for each bill under their own keys.
            if run.get("parent_run_id") is None and (binding.get("handler") == "accounts.bill"
                                                    or (not binding and run.get("workflow_key") == "bill-entry")):
                from .accounts.attention import stopped
                stopped(connection, run, user["id"])
    task = connection.execute("UPDATE tasks SET control_state=%s,updated_at=now() WHERE tenant_id=%s AND id=%s RETURNING *",
                              (target, tenant_id, task_id)).fetchone()
    if action == "resume":
        from .runtime.application import binding_for, get_handler
        for run in runs:
            if run.get("parent_run_id") is None:
                resume = getattr(get_handler(binding_for(run).handler), "on_resume", None)
                if resume:
                    resume(connection, run, user)
        task = connection.execute("SELECT * FROM tasks WHERE tenant_id=%s AND id=%s", (tenant_id, task_id)).fetchone()
        # A cloud worker may have drained/acknowledged the queue while paused.
        # Resume must durably wake it even when no run state changes.
        connection.execute("UPDATE worker_wakeup SET generation=generation+1 WHERE singleton")
    summary = {"pause": "Paused. An operation already underway may finish.",
               "resume": "Resumed from the last observed state.",
               "stop": "Stopped. Completed saves remain; an underway save may still finish."}[action]
    connection.execute("INSERT INTO task_events(tenant_id,task_id,event_type,summary,progress) VALUES (%s,%s,%s,%s,%s)",
                       (tenant_id, task_id, f"control.{action}", summary, task["progress"]))
    connection.execute("INSERT INTO event_outbox(tenant_id,event_type,aggregate_id,payload) VALUES (%s,%s,%s,%s)",
                       (tenant_id, f"task.control.{action}", task_id, Jsonb({"actor_id": str(user["id"]), "control_state": target})))
    return task


def resolve_request(connection, tenant_id, request_key, body, find_existing):
    """Serialize one tenant's launch key, then reject different-payload replay.

    The existing lookup is supplied by the domain store and must scope by tenant.
    Keep the original advisory lock key so old and new workers serialize alike.
    """
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (f"{tenant_id}:{request_key}",),
    )
    previous = find_existing(connection, tenant_id, request_key)
    if previous and previous["request_hash"] != fingerprint:
        raise ServiceError(
            "conflict", "This request key was already used for different selections."
        )
    return fingerprint, previous


def observe_task(connection, *, tenant_id, task_id, run_id, state, summary, progress, event_prefix):
    """Write UI state, timeline, and outbox together with the caller's run update."""
    connection.execute(
        """UPDATE tasks SET status=%s, summary=%s, progress=%s, updated_at=now()
            WHERE tenant_id=%s AND id=%s""",
        (TASK_STATUS[state], summary, progress, tenant_id, task_id),
    )
    connection.execute(
        """INSERT INTO task_events (tenant_id,task_id,event_type,summary,progress)
            VALUES (%s,%s,%s,%s,%s)""",
        (tenant_id, task_id, state, summary, progress),
    )
    connection.execute(
        """INSERT INTO event_outbox (tenant_id,event_type,aggregate_id,payload)
            VALUES (%s,%s,%s,%s)""",
        (
            tenant_id,
            f"{event_prefix}.{state}",
            run_id,
            Jsonb({"task_id": str(task_id), "summary": summary, "progress": progress}),
        ),
    )
