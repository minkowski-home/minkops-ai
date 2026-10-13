"""Durable per-bill hosted runs with bounded parallelism and one review task.

Children own paid sessions and recovery; the parent only aggregates persisted
outcomes. A failed extraction cannot erase successful sibling proposals.
"""

import copy
import logging
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError

from .repository import observe, run_for

log = logging.getLogger(__name__)
# Worker ticks a parent may fail before it is marked failed with attention.
AGGREGATION_ATTEMPTS = 3


def create_children(connection, run):
    connection.execute(
        "UPDATE account_runs SET config=config || '{\"batch\":true}'::jsonb WHERE id=%s",
        (run["id"],),
    )
    for file_id in run["file_ids"]:
        create_child(connection, run, file_id)


def create_child(connection, run, file_id):
    config = copy.deepcopy(run["config"])
    config.pop("batch", None)
    config.pop("retry_file_id", None)
    config.pop("tally_context_job_id", None)
    # Provider receipts belong to a particular run, including retry children.
    for field in ("hosted_workspace", "hosted_session_closed", "cleanup_attempt_at", "cleanup_attempt_count"):
        config.pop(field, None)
    config["file_ids"] = [file_id]
    config["review_mode"] = "all_outputs"
    child = connection.execute(
        """INSERT INTO account_runs
            (tenant_id,task_id,actor_id,workflow_key,definition_version,request_key,request_hash,config,file_ids,catalog_id,parent_run_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            run["tenant_id"],
            run["task_id"],
            run["actor_id"],
            run["workflow_key"],
            run["definition_version"],
            uuid4(),
            run["request_hash"],
            Jsonb(config),
            Jsonb([file_id]),
            run["catalog_id"],
            run["id"],
        ),
    ).fetchone()
    return child


def resolve_bill(connection, tenant, user, run_id, file_id, user_input, reject):
    from .repository import public_run
    from .tally_writes import complete_run, defer_input

    run = run_for(connection, tenant["id"], run_id, True)
    from minkops_platform.run_controls import require_active
    require_active(connection, tenant["id"], run["task_id"])
    if run["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Only this run's operator can resolve its bills.")
    if run["state"] != "review" or run["workflow_key"] != "bill-entry":
        raise ServiceError("conflict", "This bill run is not awaiting input.")
    unresolved = run["result"].get("unresolved", [])
    if file_id not in {i["source_file_id"] for i in unresolved}:
        raise ServiceError("invalid", "Select a bill awaiting clarification.")
    if reject:
        # A later sibling retry reaggregates children. Persist the rejection on
        # the input's children too, so their old failures cannot reappear.
        connection.execute(
            "UPDATE account_runs SET config=config || '{\"superseded\":true}'::jsonb WHERE tenant_id=%s AND parent_run_id=%s AND file_ids @> %s",
            (tenant["id"], run_id, Jsonb([file_id])),
        )
        complete_run(connection, run, defer_input(run["result"], file_id))
    else:
        if user_input.strip():
            raise ServiceError("invalid", "Edit the original system, refresh discovery, then retry.")
        original_target = run["config"].get("tally_target")
        if original_target:
            from .bills import refreshed_tally_target

            run["config"]["tally_target"] = refreshed_tally_target(
                connection, tenant, user, run["config"]["tally_target"]
            )
            if not run["config"]["tally_target"].get("schema_only"):
                connection.execute(
                    "UPDATE account_runs SET config=%s WHERE id=%s",
                    (Jsonb(run["config"]), run_id),
                )
        connection.execute(
            "UPDATE account_runs SET config=config || '{\"superseded\":true}'::jsonb WHERE tenant_id=%s AND parent_run_id=%s AND file_ids @> %s",
            (tenant["id"], run_id, Jsonb([file_id])),
        )
        child = create_child(connection, run, file_id)
        if "companies" in child["config"].get("tally_target", {}):
            from ..discovery import workflow_context
            from .client_context import context_assets

            catalog = workflow_context(
                connection, tenant["id"], child["config"]["tally_target"]["discovery_id"], ["tally"]
            )
            child["config"]["source_catalog_snapshot"] = catalog
            assets, _ = context_assets(catalog)
            # Only this continuation gets newer evidence; completed siblings retain
            # their original snapshot and verified company destinations.
            child["config"]["authorized_bindings"] = [
                b
                for b in child["config"]["authorized_bindings"]
                if not b["resource_id"].startswith("discovery-")
            ] + [
                {"capability": "files.snapshot", "resource_id": a["id"], "sha256": a["sha256"]}
                for a in assets
            ]
            connection.execute(
                "UPDATE account_runs SET config=%s WHERE id=%s",
                (Jsonb(child["config"]), child["id"]),
            )
        if child["config"].get("tally_target", {}).get("schema_only"):
            from .bills import queue_tally_context
            from ..discovery import workflow_context

            # A continuation pins the refreshed catalog independently of siblings.
            child["config"]["source_catalog_snapshot"] = workflow_context(
                connection,
                tenant["id"],
                child["config"]["tally_target"]["discovery_id"],
                ["tally"],
                tally_categories=["company", "ledgers", "voucher_types"],
            )
            connection.execute(
                "UPDATE account_runs SET config=%s WHERE id=%s",
                (Jsonb(child["config"]), child["id"]),
            )
            queue_tally_context(connection, child)
            run["config"]["tally_target"] = original_target
        connection.execute(
            "UPDATE account_runs SET config=config || jsonb_build_object('batch',true,'retry_file_id',%s::text) WHERE id=%s",
            (file_id, run_id),
        )
        observe(
            connection,
            run,
            "queued",
            "Rechecking the bill. Previously verified entries are preserved.",
            30,
        )
    return public_run(connection, run_for(connection, tenant["id"], run_id))


def reconcile_once(url):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        # NO KEY UPDATE still serializes aggregators and business mutations, but
        # lets the separate diagnostics transaction check its run foreign key.
        parents = connection.execute("""SELECT * FROM account_runs WHERE
            config->>'batch'='true' AND state IN ('queued','executing')
            AND EXISTS (SELECT 1 FROM tasks t WHERE t.tenant_id=account_runs.tenant_id AND t.id=account_runs.task_id AND t.control_state='active')
            FOR NO KEY UPDATE SKIP LOCKED""").fetchall()
        for parent in parents:
            # Every parent is a savepoint: one tenant's defect must not roll back
            # or stall other batches, nor crash the shared worker lanes.
            try:
                with connection.transaction():
                    _reconcile(connection, parent)
            except Exception as error:
                _aggregation_failed(connection, parent, error)


def _aggregation_failed(connection, parent, error):
    """Retry a bounded number of ticks for transient faults, then fail visibly."""
    from minkops_platform.runtime.diagnostics import error_details, record

    from .run_store import AccountsRunStore

    attempt = int(parent["config"].get("aggregation_failures", 0)) + 1
    record(connection, parent, "batch.aggregation_failed",
           f"Batch aggregation failed ({type(error).__name__}).", level="error",
           details={**error_details(error), "attempt": attempt})
    log.error("Batch %s aggregation failed: %s (attempt %s)", parent["id"], type(error).__name__, attempt)
    connection.execute(
        "UPDATE account_runs SET config=config || jsonb_build_object('aggregation_failures',%s::integer) WHERE id=%s",
        (attempt, parent["id"]),
    )
    if attempt >= AGGREGATION_ATTEMPTS:
        AccountsRunStore().fail(
            connection,
            parent,
            "Bill results could not be combined. Any verified saves remain; start a new run for the other bills.",
        )


def _reconcile(connection, parent):
    children = connection.execute(
        "SELECT * FROM account_runs WHERE tenant_id=%s AND parent_run_id=%s AND NOT coalesce((config->>'superseded')::boolean,false) ORDER BY file_ids->>0",
        (parent["tenant_id"], parent["id"]),
    ).fetchall()
    done = [c for c in children if c["state"] in ("review", "failed")]
    if len(done) != len(children):
        # A retry can have the same ready count as the earlier batch.
        # Enter Work again instead of leaving an active child labelled
        # as waiting to start until its extraction finishes.
        if parent["state"] == "queued" or parent["config"].get(
            "batch_finished_count"
        ) != len(done):
            connection.execute(
                "UPDATE account_runs SET config=config || jsonb_build_object('batch_finished_count',%s::integer) WHERE id=%s",
                (len(done), parent["id"]),
            )
            observe(
                connection,
                parent,
                "executing",
                f"Reading bills: {len(done)} of {len(children)} ready. Other bills continue independently.",
                20 + int(45 * len(done) / len(children)),
            )
        return
    prior = parent.get("result") or {}
    result = {"records": [], "findings": [], "unresolved": [], "deferred": list(prior.get("deferred", []))}
    result["findings"].extend(prior.get("findings", []))
    for child in children:
        file_id = child["file_ids"][0]
        previous = [r for r in prior.get("records", []) if r["source_file_id"] == file_id]
        if file_id == parent["config"].get("retry_file_id"):
            previous = [
                r for r in previous if r.get("status") in ("saved", "duplicate", "rejected")
            ]
        # The first aggregation adopts each child's outcome. Afterwards the parent
        # also holds operator decisions, so only the rechecked input is re-read.
        fresh = not prior or file_id == parent["config"].get("retry_file_id")
        carried = [i for i in prior.get("unresolved", []) if i["source_file_id"] == file_id]
        if child["state"] == "failed":
            result["records"].extend(previous)
            result["unresolved"].extend(
                [{"source_file_id": file_id, "reason": child["error"] or "Extraction needs attention."}]
                if fresh
                else carried
            )
        else:
            proposal = copy.deepcopy(child["result"])
            # A child's findings concern its one selected input, not
            # unrelated siblings. Preserve them as blocking evidence on
            # its records; client-wide policy is reapplied below.
            for record in proposal["records"]:
                record["findings"] = list(dict.fromkeys([
                    *record["findings"], *proposal["findings"]]))
                record["exception_codes"] = list(dict.fromkeys([
                    *record.get("exception_codes", []), *proposal.get("exception_codes", [])]))
            result["records"].extend(previous or proposal["records"])
            if previous and file_id == parent["config"].get("retry_file_id"):
                result["records"].extend(proposal["records"])
            result["unresolved"].extend(proposal.get("unresolved", []) if fresh else carried)
    # A single-input run also becomes a batch only when retrying a held
    # extraction. Retain unrelated outcomes not represented by children.
    covered = {c["file_ids"][0] for c in children}
    result["records"].extend(
        r for r in prior.get("records", []) if r["source_file_id"] not in covered
    )
    result["unresolved"].extend(
        i for i in prior.get("unresolved", []) if i["source_file_id"] not in covered
    )
    result["findings"] = list(dict.fromkeys(result["findings"]))
    from .tally_writes import settle_unresolved

    settle_unresolved(result)
    from minkops_platform.workflow_policies import enforce_policies

    # The parent review carries the same immutable client policy as its
    # independent children; aggregation cannot discard a review gate.
    result = enforce_policies(parent["config"], result)
    from .attention import flag, issue_record
    for issue in result.get("unresolved", []):
        flag(connection, parent, issue_record(result, issue))
    connection.execute(
        "UPDATE account_runs SET result=%s,config=config-'aggregation_failures' WHERE id=%s",
        (Jsonb(result), parent["id"]),
    )
    pending = sum(
        r.get("status") not in ("saved", "duplicate", "rejected") for r in result["records"]
    )
    observe(
        connection,
        parent,
        "review",
        f"{pending} bill entries ready; {len(result['unresolved'])} bills need attention.",
        70,
    )
    if parent["config"].get("tally_target"):
        from .tally_writes import prepare_automatic

        prepare_automatic(connection, parent, result)
