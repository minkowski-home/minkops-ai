"""Accounts-specific contracts around shared launch/execution dispatch."""

from fnmatch import fnmatchcase
from pathlib import Path

from jsonschema import ValidationError

from minkops_connectors.excel import inspect_workbook
from minkops_platform.errors import ServiceError
from minkops_platform.runtime.assets import config_json
from minkops_platform.runtime.environments import (
    SESSION_BYTE_LIMIT,
    SESSION_FILE_LIMIT,
    exceeds_session,
)
from minkops_platform.runtime.launch import LaunchInputs
from minkops_platform.workflows import resolve_run_config

from .bills import tally_target
from .catalog import validate_catalog
from .repository import files_for


def prepare_launch(connection, tenant, user, body, workflow, definition):
    target, source_context = None, None
    is_bill = definition.metadata["handler"] == "accounts.bill"
    ids = list(map(str, body["file_ids"]))
    if len(ids) != len(set(ids)):
        raise ServiceError("invalid", "Select each file only once.")
    files = files_for(connection, tenant["id"], ids)
    if any(not f["current"] for f in files):
        raise ServiceError("conflict", "Refresh changed source files before launching.")
    source_ids = list({str(f["source_id"]) for f in files})
    selections = {**body["config"], "source_ids": source_ids}
    catalog_id = body["catalog_id"]
    if definition.metadata["handler"] == "accounts.discovery" and selections.get(
        "discovery_run_id"
    ):
        from minkops_platform.discovery import get_run

        row = get_run(connection, tenant["id"], selections["discovery_run_id"])
        if row["actor_id"] != user["id"] or not row["catalog"] or row["catalog"]["partial"]:
            raise ServiceError(
                "conflict", "Complete your native discovery before interpreting context."
            )
        source_context = row["catalog"]
        selections["source_ids"] = source_ids or [str(row["id"])]
    if definition.metadata["handler"] == "accounts.discovery":
        if any(Path(f["path"]).suffix.lower() != ".xlsx" for f in files):
            raise ServiceError("invalid", "Discovery currently accepts Excel workbooks only.")
    else:
        # Bill Entry writes the client's own voucher to Tally (bill-entry 0.14+).
        discovery_id = selections.get("discovery_id")
        if not discovery_id:
            raise ServiceError("invalid", "Confirm Tally source discovery first.")
        if tuple(map(int, definition.metadata["version"].split("."))) < (0, 14, 0):
            raise ServiceError("conflict", "This Bill Entry version is retired. Reinstall the workflow, then launch again.")
        target = tally_target(connection, tenant, user, discovery_id)
        from minkops_platform import desktop

        desktop.require_companion(
            desktop.owned_device(connection, tenant["id"], user["id"], target["device_id"]))
        from minkops_platform.discovery import workflow_context

        source_context = workflow_context(connection, tenant["id"], discovery_id, ["tally"])
        target["company_mode"] = selections.get("company_mode", "infer")
        target["locked_company_guid"] = selections.get("locked_company_guid")
        if target["company_mode"] == "locked":
            from .client_context import select_target

            try:
                select_target({}, target)
            except ValueError as error:
                raise ServiceError("invalid", str(error)) from error
        elif target["locked_company_guid"] is not None:
            raise ServiceError("invalid", "Automatic company selection cannot lock a company.")
        selections.update(
            {
                "file_ids": ids,
                "catalog_version": str(discovery_id),
                "schema_id": str(discovery_id),
                "schema_version": "1",
                "destination_id": str(discovery_id),
            }
        )
        catalog_id = None
        if any(Path(f["path"]).suffix.lower() == ".xlsx" for f in files):
            raise ServiceError("invalid", "Bill entry accepts PDFs and images.")
        if body.get("destination_device_id") and str(body["destination_device_id"]) != target["device_id"]:
            raise ServiceError("invalid", "Discovery does not belong to the selected destination PC.")
    sessions = [[f] for f in files] if is_bill else [files]
    if any(exceeds_session(session) for session in sessions):
        raise ServiceError(
            "invalid",
            f"Select a smaller scope: up to {SESSION_FILE_LIMIT} files and "
            f"{SESSION_BYTE_LIMIT // 1_000_000} MB including references per run.",
        )
    try:
        config = resolve_run_config(
            definition,
            workflow["config_values"],
            selections,
            allowed_source_ids=set(selections["source_ids"]),
            allowed_destination_ids={str(target["discovery_id"] if target else catalog_id)},
        )
    except (ValueError, ValidationError) as error:
        raise ServiceError("invalid", str(error).splitlines()[0]) from error
    if definition.metadata["handler"] == "accounts.discovery" and len(ids) > config["max_files"]:
        raise ServiceError("invalid", "Selection exceeds the configured discovery file limit.")
    if definition.metadata["handler"] == "accounts.discovery":
        for file in files:
            path = file["path"]
            if not any(
                scope == "." or path == scope or path.startswith(scope.rstrip("/") + "/")
                for scope in config["scope_paths"]
            ) or any(fnmatchcase(path, p) for p in config["exclusions"]):
                raise ServiceError(
                    "invalid",
                    "A selected file is outside the configured discovery scope or is excluded.",
                )
    if is_bill:
        fmt = config["input_format"]
        if fmt != "mixed" and any(
            (Path(f["path"]).suffix.lower() == ".pdf") != (fmt == "pdf") for f in files[: len(ids)]
        ):
            raise ServiceError(
                "invalid", "Selected bills do not match the configured input format."
            )
    if (
        definition.execution_snapshot is None
        or definition.execution_snapshot["execution"]["model"] != "gpt-6-luna"
    ):
        raise ServiceError("invalid", "Accounts workflows must use the approved gpt-6-luna model.")
    snapshots = {"tally_target": target} if is_bill else {}
    if source_context:
        snapshots[
            "local_discovery_snapshot"
            if definition.metadata["handler"] == "accounts.discovery"
            else "source_catalog_snapshot"
        ] = source_context
    if is_bill:
        # Sessions receive one routed company's evidence, never every company's.
        from .company_scope import annotate, assets_for, fixed_scope

        annotate(target, source_context)
        probe = {"tally_target": target, "source_catalog_snapshot": source_context}
        scope = fixed_scope(probe)
        largest = max(len(f["content"]) for f in files[:len(ids)])
        try:
            for company in scope or [c["references"]["company_guid"] for c in target["companies"]]:
                assets, _ = assets_for({**probe, "company_scope": [company]}, largest)
        except ValueError as error:
            raise ServiceError("invalid", f"{error} Reduce the discovery scope or hand off.") from error
        if scope:
            snapshots["company_scope"] = scope
            files += assets
        return LaunchInputs(files, ids, catalog_id, config, snapshots)
    if source_context:
        from .client_context import context_assets

        assets, _ = context_assets(source_context)
        files += assets
        if exceeds_session(files):
            raise ServiceError(
                "invalid",
                "Complete discovery context exceeds hosted input limits. Reduce the voucher period or hand off; master records cannot be sampled.",
            )
    return LaunchInputs(files, ids, catalog_id, config, snapshots)


class AccountsHandler:
    def public_fields(self, connection, run):
        tally_writes = connection.execute(
            """SELECT id,device_id,company,record_index,outcome,verified_at,finished_at,cancelled_at
            FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s ORDER BY created_at""",
            (run["tenant_id"], run["id"]),
        ).fetchall()
        return {"tally_writes": tally_writes}

    queued_summary = "Queued for Accounts desk."
    executing_summary = "Accounts desk is inspecting the selected files."
    prepare_launch = staticmethod(prepare_launch)


class DiscoveryHandler(AccountsHandler):
    def prepare(self, connection, run):
        files = files_for(connection, run["tenant_id"], run["file_ids"])
        context = {"config": run["config"], "definition_version": run["definition_version"]}
        if run["config"].get("local_discovery_snapshot"):
            from .client_context import context_assets

            assets, manifest = context_assets(run["config"]["local_discovery_snapshot"])
            files += assets
            context["local_discovery"] = manifest
            context["config"] = {
                k: v for k, v in run["config"].items() if k != "local_discovery_snapshot"
            }
        context["inventory"] = [
            {"file_id": str(f["id"]), "sheets": inspect_workbook(bytes(f["content"]))}
            for f in files
            if f["path"].endswith(".xlsx")
        ]
        context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
        return files, context, {}

    def validate(self, run, files, context, domain, result):
        validate_catalog(
            result,
            {str(f["id"]): bytes(f["content"]) for f in files if f["path"].endswith(".xlsx")},
            review_proposal=True,
        )
        # Missing sheets must be visible; don't silently call a partial scan complete.
        expected = {
            (str(f["id"]), s["sheet"], t["name"] if t else None)
            for f in files
            if f["path"].endswith(".xlsx")
            for s in inspect_workbook(bytes(f["content"]))
            for t in (s["tables"] or [None])
        }
        actual = {(s["file_id"], s["sheet"], s.get("table")) for s in result["sheets"]}
        if expected != actual:
            raise ValueError("Discovery did not account for every selected worksheet.")
        if run["config"].get("local_discovery_snapshot"):
            from .client_context import validate_notes

            validate_notes(
                result.get("context_notes", []), run["config"]["local_discovery_snapshot"]
            )
        return result

    def finish(self, connection, store, run, context, domain, result):
        store.observe(connection, run, "review", "Review the discovered mappings.", 70)


class BillHandler(AccountsHandler):
    def on_resume(self, connection, run, user):
        from .attention import resume_suppliers
        resume_suppliers(connection, run, user)

    def public_fields(self, connection, run):
        from .bill_decisions import public_result
        from .bill_review import attention_items, review
        return {**super().public_fields(connection, run), "review": review(run, attention_items(connection, run)),
                "result": public_result(run)}

    def launched(self, connection, run):
        from .company_scope import needs_triage

        if len(run["file_ids"]) == 1 and run["config"].get("company_scope"):
            # A single bill posts in this run itself, with its company's pattern.
            from .posting_profiles import attach

            config = dict(run["config"])
            attach(connection, run, config, config["company_scope"][0])
            connection.execute("UPDATE workflow_runs SET config=%s WHERE id=%s", (config_json(connection, run["tenant_id"], config), run["id"]))
            run["config"] = config
            return
        if len(run["file_ids"]) > 1 or needs_triage(run["config"]):
            from .batch import create_children

            create_children(connection, run)

    def prepare(self, connection, run):
        files = files_for(connection, run["tenant_id"], run["file_ids"])
        context = {"config": run["config"], "definition_version": run["definition_version"]}
        if run["config"].get("stage") == "posting_profile":
            from .company_scope import assets_for

            assets, manifest = assets_for(run["config"], 0)
            guid = run["config"]["company_scope"][0]
            company = next(c for c in run["config"]["tally_target"]["companies"] if c["references"]["company_guid"] == guid)
            context["config"] = {k: v for k, v in run["config"].items()
                                 if k not in ("source_catalog_snapshot", "agent_output_schema")}
            context.update(source_catalog=manifest, company={"company_guid": guid, "name": company["company"]},
                           files=[{"id": a["id"], "path": a["path"]} for a in assets])
            return assets, context, {}
        if run["config"].get("stage") == "triage":
            from .company_scope import directory

            # Routing reads the bills against a compact directory, not full discovery.
            context["config"] = {k: v for k, v in run["config"].items()
                                 if k not in ("source_catalog_snapshot", "tally_target", "agent_output_schema")}
            context["company_directory"] = directory(run["config"]["source_catalog_snapshot"])
            context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
            return files, context, {}
        if run["config"].get("source_catalog_snapshot"):
            from .client_context import context_assets
            from .company_scope import assets_for

            assets, manifest = (assets_for(run["config"], sum(len(f["content"]) for f in files))
                                if run["config"].get("company_scope")
                                else context_assets(run["config"]["source_catalog_snapshot"]))
            files += assets
            context["source_catalog"] = manifest
            context["config"] = {
                k: v for k, v in run["config"].items() if k != "source_catalog_snapshot"
            }
        context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
        return files, context, {}

    def validate(self, run, files, context, domain, result):
        from .checks import adopt_exceptions

        if run["config"].get("stage") == "posting_profile":
            from .posting_profiles import masters_for, validate

            guid = run["config"]["company_scope"][0]
            return {"profile": validate(result, masters_for(run["config"], guid), guid)}
        if run["config"].get("stage") == "triage":
            known = {c["references"]["company_guid"] for c in run["config"]["tally_target"]["companies"]}
            routed = [b["source_file_id"] for b in result["bills"]]
            if sorted(routed) != sorted(run["file_ids"]) or any(
                    b["company_guid"] not in known and b["company_guid"] is not None for b in result["bills"]):
                raise ValueError("Routing must name each selected bill once and only discovered companies.")
            return result
        result = adopt_exceptions(result)
        if any(r.get("operation") != "append" for r in result.get("records", [])):
            raise ValueError(
                "Agent proposals must append by default; edits require explicit review."
            )
        if not run["config"].get("tally_target"):
            raise ValueError("Excel bill destinations are retired. Start a new Tally bill run.")
        from .bills import capture_tally_findings
        from .checks import check_voucher_records

        if any("voucher" not in r for r in result.get("records", [])):
            raise ValueError("Tally proposals must state the document and its voucher.")
        check_voucher_records(result, run["file_ids"])
        return capture_tally_findings(result, run["config"])

    def finish(self, connection, store, run, context, domain, result):
        if run["config"].get("stage") == "triage":
            store.observe(connection, run, "review", "Bills routed to their companies.", 70)
            return
        if run["config"].get("stage") == "posting_profile":
            from .posting_profiles import proposed

            proposed(connection, run, result["profile"])
            store.observe(connection, run, "review", "Posting pattern ready for one confirmation.", 70)
            return
        if run["config"].get("posting_profiles"):
            from .posting_profiles import misses

            misses(connection, run, result)
        from .bill_decisions import pin_decisions
        result = pin_decisions(run, result)
        store.save_result(connection, run, result)
        if not run.get("parent_run_id"):
            from .attention import flag, issue_record
            for issue in result.get("unresolved", []):
                flag(connection, run, issue_record(result, issue))

        store.observe(
            connection,
            run,
            "review",
            "Review bill values, source evidence and proposed destination entries.",
            70,
        )
        if not run.get("parent_run_id"):
            from .tally_writes import prepare_automatic

            prepare_automatic(connection, run, result)
