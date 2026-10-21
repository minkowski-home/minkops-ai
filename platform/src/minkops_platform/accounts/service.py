"""Accounts application services. Callers supply an authorized tenant and actor.

Transactions belong to the caller, so HTTP and worker execution retain the same
commit/rollback boundaries without depending on one another.
"""

import json
from pathlib import Path

from jsonschema import ValidationError
from psycopg.types.json import Jsonb

from minkops_connectors.excel import open_workbook
from minkops_platform.errors import ServiceError
from minkops_platform.runtime.application import binding_for, enforce_policies, get_handler
from minkops_platform.runtime.assets import config_json
from minkops_platform.workflows import load_definition as load_definition

from .catalog import validate_catalog
from .repository import digest_bytes, files_for, observe, public_run, run_for, safe_path

SUPPORTED = {".xlsx", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def launch_run(connection, tenant, user, body, *, task_id=None):
    from minkops_platform.runtime.launch import launch_run as launch

    return launch(connection, tenant, user, body, task_id=task_id)


def approve_run(connection, tenant, user, run_id, body):
    run = run_for(connection, tenant["id"], run_id, True)
    from minkops_platform.run_controls import require_active
    require_active(connection, tenant["id"], run["task_id"])
    binding = binding_for(run)
    if binding.handler == "accounts.bill" and run["actor_id"] != user["id"]:
        raise ServiceError(
            "forbidden", "Only the operator who started this bill run can approve its writes."
        )
    if run["state"] != "review":
        raise ServiceError("conflict", "This run is not awaiting review.")
    if binding.handler not in ("accounts.discovery", "accounts.bill"):
        try:
            get_handler(binding.handler).approve(connection, tenant, user, run, body)
        except (ValueError, ValidationError) as error:
            raise ServiceError("invalid", str(error).splitlines()[0]) from error
        return public_run(connection, run_for(connection, tenant["id"], run_id))
    try:
        if binding.handler == "accounts.discovery":
            files = files_for(connection, tenant["id"], run["file_ids"])
            if any(not f["current"] for f in files):
                raise ValueError("Source files changed. Run discovery again before confirming.")
            validate_catalog(body["result"], {str(f["id"]): bytes(f["content"]) for f in files})
            if run["config"].get("local_discovery_snapshot"):
                from .client_context import validate_notes

                validate_notes(
                    body["result"].get("context_notes", []),
                    run["config"]["local_discovery_snapshot"],
                )
            catalog = connection.execute(
                """INSERT INTO account_catalogs (tenant_id,actor_id,definition_version,catalog)
                  VALUES (%s,%s,%s,%s) RETURNING id""",
                (tenant["id"], user["id"], run["definition_version"], Jsonb(body["result"])),
            ).fetchone()
            connection.execute(
                "UPDATE account_runs SET catalog_id=%s WHERE tenant_id=%s AND id=%s",
                (catalog["id"], tenant["id"], run["id"]),
            )
            state, message = "completed", "Source mappings confirmed."
        else:
            tally = run["config"].get("tally_target")
            if not tally:
                raise ValueError("Excel bill destinations are retired. Start a new Tally bill run.")
            # Only the decision is editable. Source evidence, routing and the
            # proposed voucher originate from the agent result.
            original = run["result"]
            if len(body["result"].get("records", [])) != len(original["records"]):
                raise ValueError("Review must retain every extracted record.")
            reviewed = json.loads(json.dumps(original))
            for old, edited in zip(reviewed["records"], body["result"]["records"], strict=True):
                if old.get("status") in ("saved", "duplicate", "rejected"):
                    continue
                decision = edited.get("decision", "approve")
                if decision not in ("approve", "hold", "reject"):
                    raise ValueError("Choose approve, hold or reject for each bill.")
                old["decision"] = decision
                for field in ("source_file_id", "evidence", "company_guid", "company_evidence", "document", "voucher"):
                    if edited.get(field) != old.get(field):
                        raise ValueError("Review may change only the decision, not source evidence or routing.")
                if edited.get("operation", old["operation"]) != old["operation"]:
                    raise ValueError("Edit accounting values in the original system, not Minkops.")
            from .bills import recheck_target

            run["config"]["tally_target"] = recheck_target(connection, tenant, user, tally)
            connection.execute(
                "UPDATE account_runs SET config=%s WHERE id=%s",
                (config_json(connection, run["tenant_id"], run["config"]), run["id"]),
            )
            # Voucher proposals are bound and checked in prepare(); coverage only here.
            from .checks import check_voucher_records

            checked = check_voucher_records(reviewed, run["file_ids"])
            if (checked["findings"] or any(r["findings"] for r in checked["records"])) and not body[
                "acknowledge_findings"
            ]:
                raise ValueError("Acknowledge unresolved findings before approving these entries.")
            checked = enforce_policies(run["config"], checked)
            from . import tally_writes

            tally_writes.prepare(connection, run, checked, approved=True)
            body["result"] = checked
            tally_writes.complete_run(connection, run, checked)
        connection.execute(
            """UPDATE account_runs SET result=%s, review_actor_id=%s, reviewed_at=now()
             WHERE tenant_id=%s AND id=%s""",
            (Jsonb(body["result"]), user["id"], tenant["id"], run["id"]),
        )
        if binding.handler == "accounts.discovery":
            observe(connection, run, state, message, 100 if state == "completed" else 85)
    except (ValueError, ValidationError, KeyError, TypeError) as error:
        raise ServiceError("invalid", str(error).splitlines()[0]) from error
    return public_run(connection, run_for(connection, tenant["id"], run_id))


def upload_source(
    connection,
    tenant,
    user,
    names,
    contents,
    label,
    writable,
    source_id=None,
    *,
    refresh_extensions=None,
    schema_only=False,
):
    try:
        if (
            not isinstance(names, list)
            or len(names) != len(contents)
            or not 1 <= len(contents) <= 100
        ):
            raise ValueError("Choose between 1 and 100 files with their relative paths.")
        names = [safe_path(p) for p in names]
        if len(names) != len(set(names)):
            raise ValueError("Source paths must be unique.")
        if not label.strip() or len(label) > 120:
            raise ValueError("Source label must contain 1–120 characters.")
        data = contents
        for name, content in zip(names, contents, strict=True):
            if Path(name).suffix.lower() not in SUPPORTED:
                raise ValueError("Only .xlsx, PDF, PNG, JPEG and WebP files are supported.")
            if not content or len(content) > 5_000_000:
                raise ValueError("Each file must be nonempty and at most 5 MB.")
            if schema_only:
                from minkops_connectors.excel import schema_projection

                if Path(name).suffix.lower() != ".xlsx":
                    raise ValueError("Schema connections accept Excel headers only.")
                schema_projection(content)
            if Path(name).suffix.lower() == ".xlsx":
                open_workbook(content)
            elif Path(name).suffix.lower() == ".pdf" and not content.startswith(b"%PDF-"):
                raise ValueError("The selected PDF is invalid.")
            elif Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and not (
                content.startswith(b"\x89PNG\r\n\x1a\n")
                or content.startswith(b"\xff\xd8\xff")
                or (content.startswith(b"RIFF") and content[8:12] == b"WEBP")
            ):
                raise ValueError("The selected image is invalid.")
        if sum(map(len, data)) > 30_000_000:
            raise ValueError("A source refresh is limited to 30 MB.")
    except (ValueError, TypeError, KeyError) as error:
        raise ServiceError("invalid", str(error)) from error
    if source_id:
        source = connection.execute(
            "SELECT * FROM account_sources WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (tenant["id"], source_id),
        ).fetchone()
        if not source:
            raise ServiceError("not_found", "Source not found.")
        if source["actor_id"] != user["id"] and not user["is_platform_admin"]:
            raise ServiceError("forbidden", "Only the source owner can refresh this local folder.")
        if source["writable"] != writable:
            raise ServiceError("invalid", "A source cannot change its write capability.")
    else:
        source = connection.execute(
            """INSERT INTO account_sources (tenant_id,actor_id,label,writable)
              VALUES (%s,%s,%s,%s) RETURNING *""",
            (tenant["id"], user["id"], label, writable),
        ).fetchone()
    if refresh_extensions is None:
        connection.execute(
            "UPDATE account_files SET current=false WHERE tenant_id=%s AND source_id=%s AND current",
            (tenant["id"], source["id"]),
        )
    else:
        # Discovery refreshes Excel without invalidating unrelated bill snapshots.
        connection.execute(
            "UPDATE account_files SET current=false WHERE tenant_id=%s AND source_id=%s AND current AND lower(substring(path from '\\.[^.]+$'))=ANY(%s)",
            (tenant["id"], source["id"], refresh_extensions),
        )
    saved = []
    for path, content in zip(names, data, strict=True):
        saved.append(
            connection.execute(
                """INSERT INTO account_files (tenant_id,source_id,path,sha256,content,schema_only)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,source_id,path,sha256)
            DO UPDATE SET current=true,schema_only=EXCLUDED.schema_only RETURNING id,path,sha256""",
                (tenant["id"], source["id"], path, digest_bytes(content), content, schema_only),
            ).fetchone()
        )
    return {"id": source["id"], "label": source["label"], "writable": writable, "files": saved}
