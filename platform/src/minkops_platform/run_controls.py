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
