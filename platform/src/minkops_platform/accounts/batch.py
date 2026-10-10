"""Durable per-bill hosted runs with bounded parallelism and one review task.

Children own paid sessions and recovery; the parent only aggregates persisted
outcomes. A failed extraction cannot erase successful sibling proposals.
"""

import copy
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError

from .repository import observe, run_for


def create_children(connection, run):
    connection.execute(
        "UPDATE account_runs SET config=config || '{\"batch\":true}'::jsonb WHERE id=%s",
        (run["id"],),
    )
    for file_id in run["file_ids"]:
        create_child(connection, run, file_id)


def create_child(connection, run, file_id, *, user_input=None):
    config = copy.deepcopy(run["config"])
    config.pop("batch", None)
    config.pop("retry_file_id", None)
    config.pop("tally_context_job_id", None)
    if user_input:
        config["user_input"] = user_input
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
    from .tally_writes import complete_run

    run = run_for(connection, tenant["id"], run_id, True)
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
        run["result"]["unresolved"] = [i for i in unresolved if i["source_file_id"] != file_id]
        run["result"]["findings"].append(f"Operator rejected input {file_id}; it was not written.")
        complete_run(connection, run, run["result"])
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
        parents = connection.execute("""SELECT * FROM account_runs WHERE
            config->>'batch'='true' AND state IN ('queued','executing')
            FOR UPDATE SKIP LOCKED""").fetchall()
        for parent in parents:
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
                continue
            result = {"records": [], "findings": [], "unresolved": []}
            prior = parent.get("result") or {}
            result["findings"].extend(prior.get("findings", []))
            for child in children:
                file_id = child["file_ids"][0]
                previous = [r for r in prior.get("records", []) if r["source_file_id"] == file_id]
                if file_id == parent["config"].get("retry_file_id"):
                    previous = [
                        r for r in previous if r.get("status") in ("saved", "duplicate", "rejected")
                    ]
                if child["state"] == "failed":
                    result["records"].extend(previous)
                    result["unresolved"].append(
                        {
                            "source_file_id": child["file_ids"][0],
                            "reason": child["error"] or "Extraction needs attention.",
                        }
                    )
                else:
                    proposal = child["result"]
                    result["records"].extend(previous or proposal["records"])
                    if previous and file_id == parent["config"].get("retry_file_id"):
                        result["records"].extend(proposal["records"])
                    result["findings"].extend(proposal["findings"])
                    result["unresolved"].extend(proposal.get("unresolved", []))
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
            from minkops_platform.workflow_policies import enforce_policies

            # The parent review carries the same immutable client policy as its
            # independent children; aggregation cannot discard a review gate.
            result = enforce_policies(parent["config"], result)
            from .attention import flag
            for issue in result.get("unresolved", []):
                record = next((r for r in result["records"] if r["source_file_id"] == issue["source_file_id"]),
                              {"source_file_id": issue["source_file_id"], "data": {}, "findings": [issue["reason"]]})
                flag(connection, parent, record)
            connection.execute(
                "UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(result), parent["id"])
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
