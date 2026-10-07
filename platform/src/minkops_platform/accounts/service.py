"""Accounts application services. Callers supply an authorized tenant and actor.

Transactions belong to the caller, so HTTP and worker execution retain the same
commit/rollback boundaries without depending on one another.
"""

import json
from pathlib import Path

from jsonschema import ValidationError
from minkops_connectors.excel import open_workbook
from psycopg import errors
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError
from minkops_platform.runtime.application import binding_for, enforce_policies, get_handler
from minkops_platform.workflows import load_definition as load_definition

from .catalog import apply_records, validate_catalog
from .checks import check_records
from .repository import (
    catalog_contents,
    digest_bytes,
    files_for,
    observe,
    public_run,
    run_for,
    safe_path,
)

SUPPORTED = {".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def launch_run(connection, tenant, user, body, *, task_id=None):
    from minkops_platform.runtime.launch import launch_run as launch

    return launch(connection, tenant, user, body, task_id=task_id)


def approve_run(connection, tenant, user, run_id, body, *, require_destination=True):
    run = run_for(connection, tenant["id"], run_id, True)
    if run["state"] != "review":
        raise ServiceError("conflict", "This run is not awaiting review.")
    try:
        handler = binding_for(run).handler
        if handler not in {"accounts.discovery", "accounts.bill"}:
            get_handler(handler).approve(connection, tenant, user, run, body)
            return public_run(connection, run_for(connection, tenant["id"], run_id))
        if binding_for(run).handler == "accounts.discovery":
            files = files_for(connection, tenant["id"], run["file_ids"])
            if any(not f["current"] for f in files):
                raise ValueError("Source files changed. Run discovery again before confirming.")
            validate_catalog(body["result"], {str(f["id"]): bytes(f["content"]) for f in files})
            destinations = {
                s["file_id"] for s in body["result"]["sheets"] if s["role"] == "destination"
            }
            if require_destination and not destinations:
                raise ValueError("Confirm at least one bill-entry destination.")
            if any(not f["writable"] for f in files if str(f["id"]) in destinations):
                raise ValueError(
                    "Destination workbooks need a connected local folder with write permission."
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
            state, message = (
                "completed",
                "Source mappings confirmed." + (" Bill entry is ready." if destinations else ""),
            )
        else:
            # Only data and operation are editable. Source evidence and routing
            # originate from the agent result, preventing fabricated approvals.
            original = run["result"]
            if original.get("unresolved"):
                raise ValueError(
                    "Destination recognition is unresolved. Update source mappings and run bill entry again."
                )
            if len(body["result"].get("records", [])) != len(original["records"]):
                raise ValueError("Review must retain every extracted record.")
            reviewed = json.loads(json.dumps(original))
            for old, edited in zip(reviewed["records"], body["result"]["records"], strict=True):
                for field in (
                    "source_file_id",
                    "destination_file_id",
                    "sheet",
                    "table",
                    "evidence",
                ):
                    if edited.get(field) != old.get(field):
                        raise ValueError(
                            "Review may change values and append/edit choice, not source evidence or routing."
                        )
                if any(
                    edited["data"].get(k) != old["data"].get(k)
                    for k in old.get("derived_fields", {})
                ):
                    raise ValueError(
                        "Application-generated entry IDs cannot be changed in bill review."
                    )
                old["data"], old["operation"] = edited["data"], edited["operation"]
            catalog = run["config"]["catalog_snapshot"]
            files, contents = catalog_contents(connection, tenant["id"], catalog)
            checked = check_records(
                reviewed, catalog, run["file_ids"], contents, run["config"]["checks"]
            )
            if (checked["findings"] or any(r["findings"] for r in checked["records"])) and not body[
                "acknowledge_findings"
            ]:
                raise ValueError("Acknowledge unresolved findings before approving these entries.")
            prepare_writes(connection, run, checked, catalog, files, contents, approved=True)
            body["result"] = checked
            state, message = (
                "writing",
                "Approved. Waiting for verified writes to the connected local folder.",
            )
        connection.execute(
            """UPDATE account_runs SET result=%s, review_actor_id=%s, reviewed_at=now()
             WHERE tenant_id=%s AND id=%s""",
            (Jsonb(body["result"]), user["id"], tenant["id"], run["id"]),
        )
        observe(connection, run, state, message, 100 if state == "completed" else 85)
    except (ValueError, ValidationError, KeyError, TypeError) as error:
        raise ServiceError("invalid", str(error).splitlines()[0]) from error
    except errors.UniqueViolation as error:
        raise ServiceError(
            "conflict", "Another approved run is waiting to write this workbook. Complete it first."
        ) from error
    return public_run(connection, run_for(connection, tenant["id"], run_id))


def prepare_writes(connection, run, result, catalog, files, contents, *, approved=False):
    checked = enforce_policies(run["config"], result)
    if checked.get("requires_review") and not approved:
        raise ValueError("Client policy requires explicit review before writing.")
    destinations = {}
    for record in result["records"]:
        destinations.setdefault(record["destination_file_id"], []).append(record)
    for file_id, records in destinations.items():
        file = next(f for f in files if str(f["id"]) == file_id)
        if not file["writable"] or not file["current"]:
            raise ValueError(
                "Destination is disconnected or changed. Refresh discovery before writing."
            )
        # Lock source metadata so a refresh cannot interleave with approval.
        connection.execute(
            "SELECT id FROM account_sources WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (run["tenant_id"], file["source_id"]),
        )
        current = connection.execute(
            "SELECT current FROM account_files WHERE tenant_id=%s AND id=%s",
            (run["tenant_id"], file["id"]),
        ).fetchone()
        if not current["current"]:
            raise ValueError("Destination changed before approval.")
        output, changes = contents[file_id], []
        for mapping in catalog["sheets"]:
            selected = [
                r
                for r in records
                if r["sheet"] == mapping["sheet"] and r.get("table") == mapping.get("table")
            ]
            if mapping["file_id"] == file_id and selected:
                output, written = apply_records(output, mapping, selected)
                changes.extend(written)
        connection.execute(
            """INSERT INTO account_writes
            (tenant_id,run_id,file_id,source_id,path,before_sha256,after_sha256,content,changes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                run["tenant_id"],
                run["id"],
                file["id"],
                file["source_id"],
                file["path"],
                file["sha256"],
                digest_bytes(output),
                output,
                Jsonb(changes),
            ),
        )


def verify_write(connection, tenant, run_id, write_id, content):
    run = run_for(connection, tenant["id"], run_id, True)
    row = connection.execute(
        """SELECT * FROM account_writes
         WHERE tenant_id=%s AND run_id=%s AND id=%s FOR UPDATE""",
        (tenant["id"], run_id, write_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Write not found.")
    if digest_bytes(content) != row["after_sha256"]:
        raise ServiceError("conflict", "Saved workbook does not match the approved changes.")
    if not row["verified_at"]:
        connection.execute(
            "SELECT id FROM account_sources WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (tenant["id"], row["source_id"]),
        )
        connection.execute(
            "UPDATE account_files SET current=false WHERE tenant_id=%s AND source_id=%s AND path=%s",
            (tenant["id"], row["source_id"], row["path"]),
        )
        connection.execute(
            """INSERT INTO account_files (tenant_id,source_id,path,sha256,content)
             VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,source_id,path,sha256) DO UPDATE SET current=true""",
            (tenant["id"], row["source_id"], row["path"], row["after_sha256"], content),
        )
        connection.execute(
            "UPDATE account_writes SET verified_at=now() WHERE tenant_id=%s AND id=%s",
            (tenant["id"], write_id),
        )
    pending = connection.execute(
        "SELECT count(*) AS n FROM account_writes WHERE tenant_id=%s AND run_id=%s AND verified_at IS NULL AND cancelled_at IS NULL",
        (tenant["id"], run_id),
    ).fetchone()["n"]
    if not pending and run["state"] == "writing":
        observe(connection, run, "completed", "Excel entries saved in place and verified.", 100)
    return public_run(connection, run_for(connection, tenant["id"], run_id))


def cancel_writes(connection, tenant, run_id):
    run = run_for(connection, tenant["id"], run_id, True)
    if run["state"] != "writing":
        raise ServiceError("conflict", "This run has no pending local writes.")
    connection.execute(
        """UPDATE account_writes SET cancelled_at=now() WHERE tenant_id=%s
         AND run_id=%s AND verified_at IS NULL""",
        (tenant["id"], run_id),
    )
    message = "Remaining saves cancelled. Inspect the local workbooks before refreshing discovery; already applied changes remain."
    connection.execute(
        "UPDATE account_runs SET error=%s WHERE tenant_id=%s AND id=%s",
        (message, tenant["id"], run_id),
    )
    observe(connection, run, "failed", message, 85)
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
                """INSERT INTO account_files (tenant_id,source_id,path,sha256,content)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,source_id,path,sha256)
            DO UPDATE SET current=true RETURNING id,path,sha256""",
                (tenant["id"], source["id"], path, digest_bytes(content), content),
            ).fetchone()
        )
    return {"id": source["id"], "label": source["label"], "writable": writable, "files": saved}


def write_content(connection, tenant, run_id, write_id):
    row = connection.execute(
        """SELECT content,cancelled_at FROM account_writes
         WHERE tenant_id=%s AND run_id=%s AND id=%s""",
        (tenant["id"], run_id, write_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Write not found.")
    if row["cancelled_at"]:
        raise ServiceError("conflict", "This pending write was cancelled.")
    return bytes(row["content"])
