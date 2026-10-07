"""Accounts-specific contracts around shared launch/execution dispatch."""

from fnmatch import fnmatchcase
from pathlib import Path

from jsonschema import ValidationError
from minkops_connectors.excel import inspect_workbook

from minkops_platform.errors import ServiceError
from minkops_platform.workflows import resolve_run_config

from .catalog import validate_catalog
from .checks import check_records, populate_entry_ids
from .repository import catalog_contents, files_for, resolve_catalog


def prepare_launch(connection, tenant, user, body, workflow, definition):
    ids = list(map(str, body["file_ids"]))
    if len(ids) != len(set(ids)):
        raise ServiceError("invalid", "Select each file only once.")
    files = files_for(connection, tenant["id"], ids)
    if any(not f["current"] for f in files):
        raise ServiceError("conflict", "Refresh changed source files before launching.")
    source_ids = list({str(f["source_id"]) for f in files})
    selections = {**body["config"], "source_ids": source_ids}
    catalog_id = body["catalog_id"]
    if definition.metadata["handler"] == "accounts.discovery":
        if any(Path(f["path"]).suffix.lower() != ".xlsx" for f in files):
            raise ServiceError("invalid", "Discovery currently accepts Excel workbooks only.")
    else:
        if not catalog_id:
            raise ServiceError("invalid", "Confirm a source-discovery catalog first.")
        catalog_row = connection.execute(
            "SELECT * FROM account_catalogs WHERE tenant_id=%s AND id=%s",
            (tenant["id"], catalog_id),
        ).fetchone()
        if not catalog_row:
            raise ServiceError("not_found", "Catalog not found.")
        if not any(s["role"] == "destination" for s in catalog_row["catalog"]["sheets"]):
            raise ServiceError(
                "conflict", "Confirm a Bill Entry destination in source discovery first."
            )
        discovered = connection.execute(
            "SELECT id FROM discovery_runs WHERE tenant_id=%s AND catalog->>'excel_catalog_id'=%s",
            (tenant["id"], str(catalog_id)),
        ).fetchone()
        if discovered:
            from minkops_platform.discovery import require_ready

            require_ready(connection, tenant["id"], discovered["id"], ["excel"])
        if any(Path(f["path"]).suffix.lower() == ".xlsx" for f in files):
            raise ServiceError("invalid", "Bill entry accepts PDFs and images.")
        try:
            catalog_snapshot, references, _ = resolve_catalog(
                connection, tenant["id"], catalog_row["catalog"]
            )
        except ValueError as error:
            raise ServiceError("conflict", str(error)) from error
        selections.update(
            {
                "file_ids": ids,
                "catalog_version": str(catalog_id),
                "schema_id": str(catalog_id),
                "schema_version": "1",
                "destination_id": str(catalog_id),
            }
        )
        files += references
    if len(files) > 45 or sum(len(f["content"]) for f in files) > 8_000_000:
        raise ServiceError(
            "invalid",
            "Select a smaller scope: up to 45 files and 8 MB including references per run.",
        )
    try:
        config = resolve_run_config(
            definition,
            workflow["config_values"],
            selections,
            allowed_source_ids=set(source_ids),
            allowed_destination_ids={str(catalog_id)},
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
    if definition.metadata["handler"] == "accounts.bill":
        config["catalog_snapshot"] = catalog_snapshot
        fmt = config["input_format"]
        if fmt != "mixed" and any(
            (Path(f["path"]).suffix.lower() == ".pdf") != (fmt == "pdf") for f in files[: len(ids)]
        ):
            raise ServiceError(
                "invalid", "Selected bills do not match the configured input format."
            )
        if config["output_mode"] != "excel_in_place":
            raise ServiceError("invalid", "This workflow currently supports in-place Excel output.")
    return files, ids, catalog_id, config


class AccountsHandler:
    def public_fields(self, connection, run):
        writes = connection.execute(
            """SELECT id,source_id,path,before_sha256,after_sha256,changes,verified_at,cancelled_at
            FROM account_writes WHERE tenant_id=%s AND run_id=%s ORDER BY path""",
            (run["tenant_id"], run["id"]),
        ).fetchall()
        return {"writes": writes}

    queued_summary = "Queued for Accounts desk."
    executing_summary = "Accounts desk is inspecting the selected files."
    prepare_launch = staticmethod(prepare_launch)



class DiscoveryHandler(AccountsHandler):
    def prepare(self, connection, run):
        files = files_for(connection, run["tenant_id"], run["file_ids"])
        context = {"config": run["config"], "definition_version": run["definition_version"]}
        if run["config"].get("local_discovery_snapshot"):
            context["local_discovery"] = run["config"]["local_discovery_snapshot"]
        context["inventory"] = [
            {"file_id": str(f["id"]), "sheets": inspect_workbook(bytes(f["content"]))}
            for f in files
        ]
        context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
        return files, context, {}

    def validate(self, run, files, context, domain, result):
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
        return result

    def finish(self, connection, store, run, context, domain, result):
        store.observe(connection, run, "review", "Review the discovered mappings.", 70)


class BillHandler(AccountsHandler):
    def prepare(self, connection, run):
        files = files_for(connection, run["tenant_id"], run["file_ids"])
        context = {"config": run["config"], "definition_version": run["definition_version"]}
        context["catalog"] = run["config"]["catalog_snapshot"]
        refs, contents = catalog_contents(connection, run["tenant_id"], context["catalog"])
        files += [f for f in refs if f["id"] not in {i["id"] for i in files}]
        context["files"] = [{"id": str(f["id"]), "path": f["path"]} for f in files]
        return files, context, {"refs": refs, "contents": contents}

    def validate(self, run, files, context, domain, result):
        contents = domain["contents"]
        if any(r.get("operation") != "append" for r in result.get("records", [])):
            raise ValueError(
                "Agent proposals must append by default; edits require explicit review."
            )
        result = populate_entry_ids(result, context["catalog"], run["id"])
        result = check_records(
            result, context["catalog"], run["file_ids"], contents, run["config"]["checks"]
        )
        return result

    def finish(self, connection, store, run, context, domain, result):
        from .service import prepare_writes

        store.observe(
            connection,
            run,
            "review",
            "Review bill values, source evidence and proposed Excel entries.",
            70,
        )
        if (
            run["config"]["review_mode"] == "only_exceptions"
            and not result.get("requires_review")
            and not result.get("unresolved")
            and not result["findings"]
            and not any(r["findings"] for r in result["records"])
        ):
            prepare_writes(
                connection, run, result, context["catalog"], domain["refs"], domain["contents"]
            )
            store.observe(
                connection,
                run,
                "writing",
                "Checks passed. Waiting for verified local Excel writes.",
                85,
            )
