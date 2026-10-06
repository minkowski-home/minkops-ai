"""Small durable database worker for the managed hosted agent sessions.

PostgreSQL owns the queue and run state; OpenAI owns tool use and reasoning.
Advisory locks prevent duplicate workers. A saved session is reconciled after
worker restart without replaying the user's task. Ambiguous creation failures
are surfaced for explicit intervention, never automatically resubmitted.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from minkops_connectors.excel import inspect_workbook
from psycopg.types.json import Jsonb

from minkops_platform.runtime import lifecycle

from .agent import close_session, execute
from .catalog import validate_catalog
from .checks import check_records, populate_entry_ids
from .repository import catalog_contents, files_for, observe
from .run_store import AccountsRunStore
from .service import prepare_writes

STORE = AccountsRunStore()


def process(connection, run, *, executor=execute):
    files = files_for(connection, run["tenant_id"], run["file_ids"])
    context = {
        "files": [{"id": str(f["id"]), "path": f["path"], "sha256": f["sha256"]} for f in files],
        "config": run["config"],
        "definition_version": run["definition_version"],
    }
    if run["workflow_key"] == "bill-entry":
        context["catalog"] = run["config"]["catalog_snapshot"]
        refs, contents = (
            ([], {})
            if run["config"].get("tally_target")
            else catalog_contents(connection, run["tenant_id"], context["catalog"])
        )
        files += [f for f in refs if f["id"] not in {i["id"] for i in files}]
    else:
        if run["config"].get("local_discovery_snapshot"):
            context["local_discovery"] = run["config"]["local_discovery_snapshot"]
        context["inventory"] = [
            {"file_id": str(f["id"]), "sheets": inspect_workbook(bytes(f["content"]))}
            for f in files
        ]
    context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
    observe(connection, run, "executing", "Accounts desk is inspecting the selected files.", 20)
    connection.commit()

    result = lifecycle.execute_proposal(connection, STORE, run, files, context, executor)
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
            result,
            context["catalog"],
            run["file_ids"],
            contents,
            [] if run["config"].get("tally_target") else run["config"]["checks"],
        )
        if not run["config"].get("tally_target"):
            from .bills import capture_excel_state

            capture_excel_state(result, context["catalog"], contents)
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
        else "Review bill values, source evidence and proposed destination entries.",
        70,
    )
    if (
        run["workflow_key"] == "bill-entry"
        and not run["config"].get("tally_target")
        and run["config"]["review_mode"] == "only_exceptions"
        and not result.get("unresolved")
        and not result["findings"]
        and not any(r["findings"] for r in result["records"])
    ):
        prepare_writes(connection, run, result, context["catalog"], refs, contents)
        from .tally_writes import complete_run

        complete_run(connection, run, result)
    connection.commit()
    if executor is execute:
        lifecycle.close_run(connection, STORE, run, close_session=close_session)


def work_once(url, *, executor=execute):
    from .batch import reconcile_once

    reconcile_once(url)
    worked = lifecycle.work_once(
        url, STORE, lambda connection, run: process(connection, run, executor=executor)
    )
    reconcile_once(url)
    return worked


def run_forever(url):
    def lane():
        while True:
            if not work_once(url):
                cleanup_once(url)
                time.sleep(2)

    # Each lane has its own database connection and persisted hosted session.
    # Four concurrent paid turns bound cost and provider pressure; no in-memory
    # future is the source of truth for recovery.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(lane) for _ in range(4)]
        for future in futures:
            future.result()


def cleanup_once(url):
    """Retry terminal-run environment cleanup through the shared lifecycle."""
    lifecycle.cleanup_once(url, STORE, close_session=close_session)
