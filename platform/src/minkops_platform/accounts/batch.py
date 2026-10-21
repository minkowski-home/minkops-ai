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
from minkops_platform.runtime.assets import config_json

from .repository import observe, run_for

log = logging.getLogger(__name__)
# Worker ticks a parent may fail before it is marked failed with attention.
AGGREGATION_ATTEMPTS = 3


def create_children(connection, run, file_ids=None):
    """Fan out per bill, or first route bills to companies when many are open."""
    from .company_scope import needs_triage, triage_chunks
    from .repository import files_for

    connection.execute(
        "UPDATE account_runs SET config=config || '{\"batch\":true}'::jsonb WHERE id=%s",
        (run["id"],),
    )
    file_ids = file_ids or run["file_ids"]
    if needs_triage(run["config"]):
        for chunk in triage_chunks(files_for(connection, run["tenant_id"], file_ids)):
            create_child(connection, run, chunk[0], file_ids=chunk, stage="triage")
        return
    for file_id in file_ids:
        create_child(connection, run, file_id)


def create_child(connection, run, file_id, *, config=None, file_ids=None, stage=None):
    """One hosted child: a posting session for one bill, or a triage stage over several."""
    from minkops_platform.runtime.assets import hydrate
    hydrate(connection, run)
    config = copy.deepcopy(hydrate(connection, {**run, "config": config or run["config"]})["config"])
    config.pop("batch", None)
    config.pop("retry_file_id", None)
    config.pop("retry_file_ids", None)
    # Provider receipts belong to a particular run, including retry children.
    for field in ("hosted_workspace", "hosted_session_closed", "cleanup_attempt_at", "cleanup_attempt_count", "timeout_cancel_pending"):
        config.pop(field, None)
    config.pop("stage", None)
    config.pop("expanded", None)
    file_ids = file_ids if file_ids is not None else [file_id]
    config["file_ids"] = file_ids
    config["review_mode"] = "all_outputs"
    if stage:
        from minkops_platform.runtime.bundles import stage_schema

        config["stage"] = stage
        config["agent_output_schema"] = stage_schema(config["execution_snapshot"], stage)
    else:
        config["agent_output_schema"] = run["config"].get("agent_output_schema")
    if config.get("company_scope") and config.get("source_catalog_snapshot"):
        _bind_scoped_assets(connection, run, config, file_ids)
    if not stage and config.get("company_scope") and config.get("tally_target"):
        # A posting session uses its company's confirmed pattern, or waits for it.
        from .posting_profiles import attach

        profile = attach(connection, run, config, config["company_scope"][0])
        if profile["status"] == "active":
            connection.execute(
                """UPDATE workflow_runs SET config=config || jsonb_build_object('posting_profiles',
                    coalesce(config->'posting_profiles','{}'::jsonb) || %s::jsonb) WHERE id=%s""",
                (Jsonb({config["company_scope"][0]: config["posting_profiles"][config["company_scope"][0]]}), run["id"]))
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
            config_json(connection, run["tenant_id"], config),
            Jsonb(file_ids),
            run["catalog_id"],
            run["id"],
        ),
    ).fetchone()
    return child


def _bind_scoped_assets(connection, run, config, file_ids):
    """Authorize exactly the company slice this posting session will receive."""
    from .company_scope import assets_for
    from .repository import files_for

    bills = files_for(connection, run["tenant_id"], file_ids)
    assets, _ = assets_for(config, sum(len(f["content"]) for f in bills))
    config["authorized_bindings"] = [
        b for b in config["authorized_bindings"] if not b["resource_id"].startswith("discovery-")
    ] + [{"capability": "files.snapshot", "resource_id": a["id"], "sha256": a["sha256"]} for a in assets]


def resolve_bill(connection, tenant, user, run_id, file_id, reject):
    """Defer an unresolved input, or recheck it against refreshed discovery.

    Reached only through audited Attention decisions (Do nothing, Recheck).
    """
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
        if run["config"].get("tally_target"):
            from .bills import refreshed_tally_target

            run["config"]["tally_target"] = refreshed_tally_target(
                connection, tenant, user, run["config"]["tally_target"]
            )
            connection.execute(
                "UPDATE account_runs SET config=%s WHERE id=%s",
                (config_json(connection, run["tenant_id"], run["config"]), run_id),
            )
        connection.execute(
            "UPDATE account_runs SET config=config || '{\"superseded\":true}'::jsonb WHERE tenant_id=%s AND parent_run_id=%s AND file_ids @> %s",
            (tenant["id"], run_id, Jsonb([file_id])),
        )
        from .company_scope import needs_triage
        if needs_triage(run["config"]):
            # Route the recheck against the refreshed discovery it was asked for.
            from ..discovery import workflow_context
            run["config"]["source_catalog_snapshot"] = workflow_context(
                connection, tenant["id"], run["config"]["tally_target"]["discovery_id"], ["tally"])
            from .company_scope import annotate
            annotate(run["config"]["tally_target"], run["config"]["source_catalog_snapshot"])
            create_children(connection, run, [file_id])
        else:
            create_child(connection, run, file_id)
        connection.execute(
            "UPDATE account_runs SET config=(config-'retry_file_ids') || jsonb_build_object('batch',true,'retry_file_id',%s::text) WHERE id=%s",
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


def recheck_many(connection, tenant, user, run, file_ids):
    """Refresh discovery once, then enqueue independent children atomically."""
    resolve_bill(connection, tenant, user, run["id"], file_ids[0], False)
    template = connection.execute("""SELECT config FROM account_runs WHERE tenant_id=%s
        AND parent_run_id=%s AND file_ids @> %s AND NOT coalesce((config->>'superseded')::boolean,false)
        ORDER BY updated_at DESC LIMIT 1""", (tenant["id"], run["id"], Jsonb([file_ids[0]]))).fetchone()
    from minkops_platform.runtime.assets import hydrate
    parent = hydrate(connection, {**run, "config": template["config"]})
    for file_id in file_ids[1:]:
        connection.execute("UPDATE account_runs SET config=config || '{\"superseded\":true}'::jsonb WHERE tenant_id=%s AND parent_run_id=%s AND file_ids @> %s",
            (tenant["id"], run["id"], Jsonb([file_id])))
        from .company_scope import needs_triage
        if needs_triage(parent["config"]):
            create_children(connection, parent, [file_id])
            continue
        create_child(connection, parent, file_id)
    connection.execute("UPDATE account_runs SET config=config || %s WHERE tenant_id=%s AND id=%s",
        (Jsonb({"retry_file_ids": file_ids}), tenant["id"], run["id"]))


def reconcile_once(url):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        from .posting_profiles import sweep

        with connection.transaction():
            sweep(connection)
        parents = connection.execute("""SELECT id,tenant_id FROM workflow_runs WHERE
            is_batch AND state IN ('queued','executing')
            AND EXISTS (SELECT 1 FROM tasks t WHERE t.tenant_id=workflow_runs.tenant_id AND t.id=workflow_runs.task_id AND t.control_state='active')
            ORDER BY updated_at LIMIT 100""").fetchall()
        connection.commit()
        for identity in parents:
            parent = connection.execute("""SELECT * FROM workflow_runs WHERE tenant_id=%s AND id=%s
                AND state IN ('queued','executing') FOR NO KEY UPDATE SKIP LOCKED""",
                (identity["tenant_id"], identity["id"])).fetchone()
            if not parent:
                connection.commit()
                continue
            from minkops_platform.runtime.assets import hydrate
            hydrate(connection, parent)
            # Every parent is a savepoint: one tenant's defect must not roll back
            # or stall other batches, nor crash the shared worker lanes.
            try:
                with connection.transaction():
                    _reconcile(connection, parent)
            except Exception as error:
                _aggregation_failed(connection, parent, error)
            connection.commit()


def _aggregation_failed(connection, parent, error):
    """Retry a bounded number of ticks for transient faults, then fail visibly."""
    from minkops_platform.runtime.diagnostics import error_details, record
    from minkops_platform.runtime.store import WorkflowRunStore

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
        WorkflowRunStore().fail(
            connection,
            parent,
            "Bill results could not be combined. Any verified saves remain; start a new run for the other bills.",
        )


def _reconcile(connection, parent):
    from .company_scope import expand

    stages = connection.execute(
        """SELECT id,file_ids,state,result,error,config FROM account_runs WHERE tenant_id=%s AND parent_run_id=%s
        AND config->>'stage'='triage' AND NOT coalesce((config->>'superseded')::boolean,false)
        AND NOT coalesce((config->>'expanded')::boolean,false)""",
        (parent["tenant_id"], parent["id"]),
    ).fetchall()
    for triage in stages:
        if triage["state"] in ("review", "failed"):
            from minkops_platform.runtime.assets import hydrate
            # expand consumes config as well as the validated routing result.
            triage["config"] = hydrate(connection, {**parent, **triage})["config"]
            expand(connection, parent, triage)
    if any(t["state"] not in ("review", "failed") for t in stages):
        observe(connection, parent, "executing", "Routing bills to their companies.", 15)
        return
    children = connection.execute(
        # Aggregation consumes outcomes, never the repeated multi-megabyte
        # execution catalogs pinned independently to every bill child.
        """SELECT r.id,r.file_ids,r.state,r.result,r.error,p.status='proposed' AS awaiting_confirmation
        FROM account_runs r LEFT JOIN client_profiles p ON p.tenant_id=r.tenant_id
          AND p.id::text=r.config->'awaits'->>'profile'
        WHERE r.tenant_id=%s AND r.parent_run_id=%s
          AND NOT coalesce((r.config->>'superseded')::boolean,false)
          AND r.config->>'stage' IS NULL ORDER BY r.file_ids->>0""",
        (parent["tenant_id"], parent["id"]),
    ).fetchall()
    done = [c for c in children if c["state"] in ("review", "failed")]
    if len(done) != len(children):
        waiting = sum(bool(c["awaiting_confirmation"]) for c in children
                      if c["state"] == "queued")
        # A retry can have the same ready count as the earlier batch.
        # Enter Work again instead of leaving an active child labelled
        # as waiting to start until its extraction finishes.
        if parent["state"] == "queued" or parent["config"].get(
            "batch_finished_count"
        ) != len(done) or parent["config"].get("batch_waiting_count", 0) != waiting:
            connection.execute(
                """UPDATE account_runs SET config=config || jsonb_build_object(
                    'batch_finished_count',%s::integer,'batch_waiting_count',%s::integer) WHERE id=%s""",
                (len(done), waiting, parent["id"]),
            )
            observe(
                connection,
                parent,
                "executing",
                (f"{waiting} bill{'s' if waiting != 1 else ''} waiting: confirm the posting pattern in Attention. "
                 f"{len(done)} of {len(children)} ready." if waiting else
                 f"Reading bills: {len(done)} of {len(children)} ready. Other bills continue independently."),
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
        fresh = not prior or file_id in {parent["config"].get("retry_file_id"), *parent["config"].get("retry_file_ids", [])}
        carried = [i for i in prior.get("unresolved", []) if i["source_file_id"] == file_id]
        if child["state"] == "failed":
            result["records"].extend(previous)
            result["unresolved"].extend(
                [{"source_file_id": file_id, "code": "extraction_failed", "reason": child["error"] or "Extraction needs attention."}]
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
    from .bill_decisions import pin_decisions
    result = pin_decisions(parent, result)
    from .attention import flag, issue_record
    for issue in result.get("unresolved", []):
        # Re-aggregation restates carried issues; only a recheck is a new event.
        flag(connection, parent, issue_record(result, issue),
             reopen=issue["source_file_id"] in {parent["config"].get("retry_file_id"), *parent["config"].get("retry_file_ids", [])})
    connection.execute(
        "UPDATE account_runs SET result=%s,config=config-'aggregation_failures' WHERE id=%s",
        (Jsonb(result), parent["id"]),
    )
    attention_files = {i["source_file_id"] for i in result["unresolved"]} | {
        r["source_file_id"] for r in result["records"] if r.get("exception_codes") or r.get("findings") or r.get("save_hold")}
    ready_count = sum(r.get("status") not in ("saved", "duplicate", "rejected", "writing")
                      and r["source_file_id"] not in attention_files for r in result["records"])
    observe(
        connection,
        parent,
        "review",
        f"{len(result['records'])} bill entries read; {ready_count} ready to write; {len(attention_files)} bills need attention.",
        70,
    )
    if parent["config"].get("tally_target"):
        from .tally_writes import prepare_automatic

        prepare_automatic(connection, parent, result)
