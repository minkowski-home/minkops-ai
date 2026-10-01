"""Small durable database worker for the managed hosted agent sessions.

PostgreSQL owns the queue and run state; OpenAI owns tool use and reasoning.
Advisory locks prevent duplicate workers. A saved session is reconciled after
worker restart without replaying the user's task. Ambiguous creation failures
are surfaced for explicit intervention, never automatically resubmitted.
"""

import logging
import time

import psycopg
from jsonschema import Draft202012Validator
from minkops_connectors.excel import inspect_workbook
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .agent import close_session, execute
from .catalog import validate_catalog
from .checks import check_records, populate_entry_ids
from .repository import catalog_contents, files_for, observe
from .service import prepare_writes

log = logging.getLogger(__name__)


def process(connection, run, *, executor=execute):
    files = files_for(connection, run["tenant_id"], run["file_ids"])
    context = {
        "files": [{"id": str(f["id"]), "path": f["path"], "sha256": f["sha256"]} for f in files],
        "config": run["config"],
        "definition_version": run["definition_version"],
    }
    if run["workflow_key"] == "bill-entry":
        context["catalog"] = run["config"]["catalog_snapshot"]
        refs, contents = catalog_contents(connection, run["tenant_id"], context["catalog"])
        files += [f for f in refs if f["id"] not in {i["id"] for i in files}]
    else:
        context["inventory"] = [
            {"file_id": str(f["id"]), "sheets": inspect_workbook(bytes(f["content"]))}
            for f in files
        ]
    context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
    observe(connection, run, "executing", "Accounts desk is inspecting the selected files.", 20)
    connection.commit()

    def on_event(kind, session_id, turn_id):
        connection.execute(
            """UPDATE account_runs SET session_id=coalesce(%s,session_id),
             turn_id=coalesce(%s,turn_id),updated_at=now() WHERE tenant_id=%s AND id=%s""",
            (session_id, turn_id, run["tenant_id"], run["id"]),
        )
        connection.commit()

    if run["session_id"] and not run["turn_id"]:
        from openai import OpenAI

        turns = list(OpenAI().beta.agents.sessions.turns.list(run["session_id"]))
        if len(turns) != 1:
            raise ValueError("Saved session requires turn reconciliation.")
        run["turn_id"] = turns[0].id
    result = executor(
        run["workflow_key"],
        files,
        context,
        on_event,
        session_id=run["session_id"],
        turn_id=run["turn_id"],
    )
    # Preserve the received proposal before validation so a failed run can be
    # diagnosed after its hosted environment is released.
    connection.execute(
        "UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s",
        (Jsonb(result), run["tenant_id"], run["id"]),
    )
    connection.commit()
    if run["config"].get("agent_output_schema"):
        Draft202012Validator(run["config"]["agent_output_schema"]).validate(result)
    if run["workflow_key"] == "source-discovery":
        validate_catalog(
            result, {str(f["id"]): bytes(f["content"]) for f in files}, review_proposal=True
        )
        # Missing sheets must be visible; don't silently call a partial scan complete.
        expected = {
            (str(f["id"]), s["sheet"], t["name"] if t else None)
            for f in files
            for s in inspect_workbook(bytes(f["content"]))
            for t in (s["tables"] or [None])
        }
        actual = {(s["file_id"], s["sheet"], s.get("table")) for s in result["sheets"]}
        if expected != actual:
            raise ValueError("Discovery did not account for every selected worksheet.")
    else:
        if any(r.get("operation") != "append" for r in result.get("records", [])):
            raise ValueError(
                "Agent proposals must append by default; edits require explicit review."
            )
        result = populate_entry_ids(result, context["catalog"], run["id"])
        result = check_records(
            result, context["catalog"], run["file_ids"], contents, run["config"]["checks"]
        )
    connection.execute(
        "UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s",
        (Jsonb(result), run["tenant_id"], run["id"]),
    )
    observe(
        connection,
        run,
        "review",
        "Review the discovered mappings."
        if run["workflow_key"] == "source-discovery"
        else "Review bill values, source evidence and proposed Excel entries.",
        70,
    )
    if (
        run["workflow_key"] == "bill-entry"
        and run["config"]["review_mode"] == "only_exceptions"
        and not result.get("unresolved")
        and not result["findings"]
        and not any(r["findings"] for r in result["records"])
    ):
        prepare_writes(connection, run, result, context["catalog"], refs, contents)
        observe(
            connection,
            run,
            "writing",
            "Checks passed. Waiting for verified local Excel writes.",
            85,
        )
    connection.commit()
    if executor is execute:
        saved = connection.execute(
            "SELECT session_id FROM account_runs WHERE id=%s", (run["id"],)
        ).fetchone()
        if saved["session_id"]:
            try:
                close_session(saved["session_id"])
                connection.execute(
                    "UPDATE account_runs SET config=config || '{\"hosted_session_closed\":true}'::jsonb WHERE id=%s",
                    (run["id"],),
                )
                connection.commit()
            except Exception as error:
                connection.rollback()
                log.warning(
                    "Session cleanup pending for run %s (%s)", run["id"], type(error).__name__
                )


def work_once(url, *, executor=execute):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        candidates = connection.execute("""SELECT * FROM account_runs WHERE state='queued'
             OR (state='executing' AND updated_at < now()-interval '30 seconds')
             ORDER BY updated_at LIMIT 10""").fetchall()
        for run in candidates:
            lock = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS held", (str(run["id"]),)
            ).fetchone()["held"]
            if not lock:
                continue
            connection.commit()
            try:
                current = connection.execute(
                    "SELECT * FROM account_runs WHERE id=%s", (run["id"],)
                ).fetchone()
                if current["state"] not in ("queued", "executing"):
                    continue
                if current["state"] == "executing" and not current["session_id"]:
                    raise ValueError(
                        "Worker stopped before a session ID was saved. Start a new run explicitly; the task will not be replayed automatically."
                    )
                process(connection, current, executor=executor)
            except Exception as error:
                connection.rollback()
                # Provider errors are logged by class, keeping credentials and
                # source text out of logs. The UI receives an actionable summary.
                message = (
                    str(error).splitlines()[0][:400]
                    if isinstance(error, ValueError)
                    else f"Hosted workflow failed ({type(error).__name__}). Check runtime access and retry explicitly."
                )
                connection.execute(
                    "UPDATE account_runs SET error=%s WHERE tenant_id=%s AND id=%s",
                    (message, run["tenant_id"], run["id"]),
                )
                observe(connection, run, "failed", message, 20)
                connection.commit()
                log.error("Run %s failed: %s", run["id"], type(error).__name__)
            finally:
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))", (str(run["id"]),)
                )
                connection.commit()
            return True
    return False


def run_forever(url):
    while True:
        if not work_once(url):
            cleanup_once(url)
            time.sleep(2)


def cleanup_once(url):
    """Retry completed/failed environment cleanup at most once a minute per run."""
    with psycopg.connect(url, row_factory=dict_row) as connection:
        row = connection.execute("""SELECT id,session_id FROM account_runs
             WHERE state NOT IN ('queued','executing') AND session_id IS NOT NULL
             AND NOT coalesce((config->>'hosted_session_closed')::boolean,false)
             AND coalesce((config->>'cleanup_attempt_at')::timestamptz,'epoch') < now()-interval '1 minute'
             ORDER BY updated_at LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if not row:
            return
        connection.execute(
            "UPDATE account_runs SET config=config || jsonb_build_object('cleanup_attempt_at',now()) WHERE id=%s",
            (row["id"],),
        )
        connection.commit()
        try:
            close_session(row["session_id"])
            connection.execute(
                "UPDATE account_runs SET config=config || '{\"hosted_session_closed\":true}'::jsonb WHERE id=%s",
                (row["id"],),
            )
            connection.commit()
        except Exception as error:
            log.warning("Session cleanup pending for run %s (%s)", row["id"], type(error).__name__)
