"""Small durable-run boundaries around the managed harness.

Stores own their tables and tenant predicates; workflow handlers own domain
validation and approvals. This module never plans work or orchestrates tools.
"""

import logging
import time
from collections import Counter
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Protocol

import psycopg
from jsonschema import Draft202012Validator
from psycopg.rows import dict_row

from .diagnostics import error_details, record, stage
from .openai_hosted import close_session as hosted_close_session
from .openai_hosted import reconcile_turn

log = logging.getLogger(__name__)
HOSTED_ACTIVITY_INTERVAL = 10


class RunStore(Protocol):
    def candidates(self, connection): ...
    def get(self, connection, tenant_id, run_id): ...
    def fail(self, connection, run, message): ...
    def save_session(self, connection, run, session_id, turn_id): ...
    def save_result(self, connection, run, result): ...
    def claim_cleanup(self, connection): ...
    def mark_closed(self, connection, run): ...


def execute_proposal(connection, store: RunStore, run, files, context, executor, *, reuse_environments=False):
    """Save raw proposals before validation, preserving failed-run diagnostics."""
    if not run["config"].get("execution_snapshot") and not run["session_id"]:
        raise ValueError("Legacy run has no pinned execution bundle. Launch a new run explicitly.")

    activity = Counter()
    last_saved = time.monotonic()

    def flush_activity():
        if activity:
            record(connection, run, "hosted.activity", "Hosted stream activity", details={
                "event_counts": dict(activity),
                "session_id": run["session_id"], "turn_id": run["turn_id"],
            })
            activity.clear()

    def on_event(kind, session_id, turn_id):
        nonlocal last_saved
        now = time.monotonic()
        session_id = session_id or run["session_id"]
        turn_id = turn_id or run["turn_id"]
        changed = (session_id, turn_id) != (run["session_id"], run["turn_id"])
        heartbeat = now - last_saved >= HOSTED_ACTIVITY_INTERVAL
        # Recovery IDs must be durable before consuming another event. Unchanged
        # IDs need only a bounded heartbeat, not a commit for every text chunk.
        if changed or heartbeat:
            store.save_session(connection, run, session_id, turn_id)
            connection.commit()
            run["session_id"], run["turn_id"] = session_id, turn_id
            last_saved = now
        if kind.endswith(".delta") or kind.startswith((
            "agent.session.turn.item.", "agent.session.turn.content_part.",
            "agent.session.turn.output_text.",
        )):
            activity[kind] += 1
            if heartbeat:
                flush_activity()
            return
        # Lifecycle milestones and failures remain individually auditable.
        flush_activity()
        record(
            connection,
            run,
            "hosted.event",
            f"Hosted session event: {kind}",
            details={
                "provider_event": kind,
                "session_id": session_id,
                "turn_id": turn_id,
            },
        )

    if run["session_id"] and not run["turn_id"]:
        run["turn_id"] = reconcile_turn(run["session_id"])
        store.save_session(connection, run, run["session_id"], run["turn_id"])
        connection.commit()
    with stage(
        connection,
        run,
        "ai",
        "Execute or reconcile hosted AI proposal",
        details={
            "resumed": bool(run["session_id"]),
            "model": run["config"].get("execution_snapshot", {}).get("execution", {}).get("model"),
            "inputs": [
                {"file_id": str(file["id"]), "bytes": len(file["content"])} for file in files
            ],
        },
    ):
        try:
            from .environments import acquire

            with acquire(connection, run) if reuse_environments else nullcontext() as lease:
                result = executor(
                    run["workflow_key"], files, context, on_event,
                    session_id=run["session_id"], turn_id=run["turn_id"],
                    **({"environment_lease": lease} if lease else {}),
                )
        finally:
            # Preserve the final counts even on disconnect or provider failure.
            flush_activity()
    store.save_result(connection, run, result)
    connection.commit()
    if run["config"].get("agent_output_schema"):
        with stage(connection, run, "schema", "Validate hosted output schema"):
            Draft202012Validator(run["config"]["agent_output_schema"]).validate(result)
    return result


def close_run(connection, store: RunStore, run, *, close_session=hosted_close_session):
    if not run["session_id"]:
        return
    try:
        with stage(connection, run, "cleanup", "Release hosted session environment"):
            close_session(run["session_id"])
            store.mark_closed(connection, run)
            connection.commit()
    except Exception as error:
        connection.rollback()
        log.warning("Session cleanup pending for run %s (%s)", run["id"], type(error).__name__)


def work_once(url, store: RunStore, process):
    """Claim at most one run, reload after locking, and never blindly replay input."""
    with psycopg.connect(url, row_factory=dict_row) as connection:
        for run in store.candidates(connection):
            held = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS held", (str(run["id"]),)
            ).fetchone()["held"]
            if not held:
                continue
            connection.commit()
            try:
                current = store.get(connection, run["tenant_id"], run["id"])
                if current["state"] not in ("queued", "executing"):
                    continue
                created = current.get("created_at")
                queued = current.get("updated_at") if current["state"] == "queued" else None
                record(
                    connection,
                    current,
                    "worker.claimed",
                    "Worker claimed durable workflow run",
                    details={
                        "previous_state": current["state"],
                        "age_ms": round((datetime.now(UTC) - created).total_seconds() * 1000)
                        if created
                        else None,
                        "queue_wait_ms": round((datetime.now(UTC) - queued).total_seconds() * 1000)
                        if queued
                        else None,
                        "parent_run_id": str(current["parent_run_id"])
                        if current.get("parent_run_id")
                        else None,
                    },
                )
                from .application import binding_for, get_handler
                binding = current['config'].get('runtime_binding')
                deterministic = bool(binding and getattr(get_handler(binding_for(current).handler), "deterministic", False))
                if current["state"] == "executing" and not current["session_id"] and not deterministic:
                    raise ValueError(
                        "Worker stopped before a session ID was saved. Start a new run explicitly; "
                        "the task will not be replayed automatically."
                    )
                process(connection, current)
            except Exception as error:
                connection.rollback()
                from minkops_platform.errors import ServiceError
                from minkops_platform.run_controls import control_state
                if isinstance(error, ServiceError) and control_state(connection, run["tenant_id"], run["task_id"]) != "active":
                    continue
                record(
                    connection,
                    run,
                    "worker.failed",
                    f"Workflow execution failed ({type(error).__name__}).",
                    level="error",
                    details=error_details(error),
                )
                message = (
                    str(error).splitlines()[0][:400]
                    if isinstance(error, ValueError)
                    else f"Hosted workflow failed ({type(error).__name__}). Check runtime access and retry explicitly."
                )
                store.fail(connection, run, message)
                connection.commit()
                log.error("Run %s failed: %s", run["id"], type(error).__name__)
            finally:
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))", (str(run["id"]),)
                )
                connection.commit()
            return True
    return False


def cleanup_once(url, store: RunStore, *, close_session=hosted_close_session):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        run = store.claim_cleanup(connection)
        connection.commit()
        if run:
            close_run(connection, store, run, close_session=close_session)
        return bool(run)
