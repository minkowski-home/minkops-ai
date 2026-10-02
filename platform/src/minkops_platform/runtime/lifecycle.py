"""Small durable-run boundaries around the managed harness.

Stores own their tables and tenant predicates; workflow handlers own domain
validation and approvals. This module never plans work or orchestrates tools.
"""

import logging
from typing import Protocol

import psycopg
from jsonschema import Draft202012Validator
from psycopg.rows import dict_row

from .openai_hosted import close_session as hosted_close_session
from .openai_hosted import reconcile_turn

log = logging.getLogger(__name__)


class RunStore(Protocol):
    def candidates(self, connection): ...
    def get(self, connection, tenant_id, run_id): ...
    def fail(self, connection, run, message): ...
    def save_session(self, connection, run, session_id, turn_id): ...
    def save_result(self, connection, run, result): ...
    def claim_cleanup(self, connection): ...
    def mark_closed(self, connection, run): ...


def execute_proposal(connection, store: RunStore, run, files, context, executor):
    """Save raw proposals before validation, preserving failed-run diagnostics."""
    if not run["config"].get("execution_snapshot") and not run["session_id"]:
        raise ValueError("Legacy run has no pinned execution bundle. Launch a new run explicitly.")

    def on_event(kind, session_id, turn_id):
        store.save_session(connection, run, session_id, turn_id)
        connection.commit()
        run["session_id"] = session_id or run["session_id"]
        run["turn_id"] = turn_id or run["turn_id"]

    if run["session_id"] and not run["turn_id"]:
        run["turn_id"] = reconcile_turn(run["session_id"])
        store.save_session(connection, run, run["session_id"], run["turn_id"])
        connection.commit()
    result = executor(
        run["workflow_key"],
        files,
        context,
        on_event,
        session_id=run["session_id"],
        turn_id=run["turn_id"],
    )
    store.save_result(connection, run, result)
    connection.commit()
    if run["config"].get("agent_output_schema"):
        Draft202012Validator(run["config"]["agent_output_schema"]).validate(result)
    return result


def close_run(connection, store: RunStore, run, *, close_session=hosted_close_session):
    if not run["session_id"]:
        return
    try:
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
                if current["state"] == "executing" and not current["session_id"]:
                    raise ValueError(
                        "Worker stopped before a session ID was saved. Start a new run explicitly; "
                        "the task will not be replayed automatically."
                    )
                process(connection, current)
            except Exception as error:
                connection.rollback()
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
