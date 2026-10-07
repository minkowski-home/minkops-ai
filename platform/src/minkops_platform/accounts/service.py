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

from .bills import tally_target
from .catalog import apply_records, validate_catalog, validate_data
from .checks import check_records, populate_entry_ids
from .repository import (
    digest_bytes,
    files_for,
    observe,
    public_run,
    resolve_catalog,
    run_for,
    safe_path,
)

SUPPORTED = {".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def launch_run(connection, tenant, user, body, *, task_id=None):
    from minkops_platform.runtime.launch import launch_run as launch

    return launch(connection, tenant, user, body, task_id=task_id)


def approve_run(connection, tenant, user, run_id, body, *, require_destination=True):
    run = run_for(connection, tenant["id"], run_id, True)
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
            tally = run["config"].get("tally_target")
            if tally:
                run["config"]["tally_target"] = tally_target(
                    connection, tenant, user, tally["discovery_id"]
                )
                connection.execute(
                    "UPDATE account_runs SET config=%s WHERE id=%s",
                    (Jsonb(run["config"]), run["id"]),
                )
                files, contents = [], {}
            else:
                discovered = connection.execute(
                    "SELECT id FROM discovery_runs WHERE tenant_id=%s AND catalog->>'excel_catalog_id'=%s",
                    (tenant["id"], str(run["catalog_id"])),
                ).fetchone()
                if discovered:
                    from minkops_platform.discovery import require_ready

                    require_ready(connection, tenant["id"], discovered["id"], ["excel"])
                catalog, files, contents = resolve_catalog(connection, tenant["id"], catalog)
                # Verified writes can advance the pinned mappings between partial approvals.
                old_catalog = run["config"]["catalog_snapshot"]
                for old_mapping, mapping in zip(
                    old_catalog["sheets"], catalog["sheets"], strict=True
                ):
                    for record in reviewed["records"]:
                        if (
                            record["destination_file_id"],
                            record["sheet"],
                            record.get("table"),
                        ) == (
                            old_mapping["file_id"],
                            old_mapping["sheet"],
                            old_mapping.get("table"),
                        ):
                            record["destination_file_id"] = mapping["file_id"]
                run["config"]["catalog_snapshot"] = catalog
                connection.execute(
                    "UPDATE account_runs SET config=%s WHERE id=%s",
                    (Jsonb(run["config"]), run["id"]),
                )
            # User edits can correct bill identity. Recompute app-owned IDs from
            # the reviewed values rather than retaining an extraction-time ID.
            populate_entry_ids(
                {
                    "records": [
                        r
                        for r in reviewed["records"]
                        if r.get("status") not in ("saved", "duplicate", "rejected")
                    ]
                },
                catalog,
                run["id"],
            )
            checked = check_records(
                reviewed,
                catalog,
                run["file_ids"],
                contents,
                [] if tally else run["config"]["checks"],
            )
            if (checked["findings"] or any(r["findings"] for r in checked["records"])) and not body[
                "acknowledge_findings"
            ]:
                raise ValueError("Acknowledge unresolved findings before approving these entries.")
            checked = enforce_policies(run["config"], checked)
            from . import tally_writes

            if tally:
                tally_writes.prepare(connection, run, checked, approved=True)
            else:
                prepare_writes(connection, run, checked, catalog, files, contents, approved=True)
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
    except errors.UniqueViolation as error:
        raise ServiceError(
            "conflict", "Another approved run is waiting to write this workbook. Complete it first."
        ) from error
    return public_run(connection, run_for(connection, tenant["id"], run_id))


def prepare_writes(connection, run, result, catalog, files, contents, *, approved=False):
    checked = enforce_policies(run["config"], result)
    if checked.get("requires_review") and not approved:
        raise ValueError("Client policy requires explicit review before destination writes.")
    from minkops_connectors.excel import sheet_records

    from .bills import classify_excel, excel_matches, same_value

    destinations = {}
    for record in result["records"]:
        if record.get("status") in ("saved", "duplicate", "rejected", "writing"):
            continue
        if record.get("decision") == "reject":
            record["status"] = "rejected"
            continue
        if record.get("decision") == "hold":
            record["status"] = "held"
            continue
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
                for record in selected:
                    try:
                        validate_data(mapping, record["data"])
                        classification = classify_excel(
                            record["data"], mapping, sheet_records(output, mapping)
                        )
                        if classification == "correction":
                            existing = excel_matches(
                                record["data"], mapping, sheet_records(output, mapping)
                            )[0]
                            expected = record.get("expected_excel")
                            record["current_excel"] = existing
                            record["expected_excel"] = existing
                            if record["operation"] == "update":
                                if not expected or any(
                                    not same_value(expected.get(k), v) for k, v in existing.items()
                                ):
                                    raise ValueError(
                                        "Destination values changed after extraction. Review the observed values before approving this correction."
                                    )
                                record["match_data"] = {
                                    k: existing[k] for k in mapping["key_columns"]
                                }
                        if classification == "duplicate":
                            record["status"] = "duplicate"
                            record["findings"].append(
                                "Exact duplicate already exists; no additional row was created."
                            )
                            continue
                        if classification == "ambiguous" or (
                            classification == "correction" and record["operation"] != "update"
                        ):
                            raise ValueError(
                                "Existing bill differs or has ambiguous keys. Review an explicit edit."
                            )
                        output, written = apply_records(output, mapping, [record])
                        for change in written:
                            change["record_index"] = result["records"].index(record)
                        changes.extend(written)
                        record["status"] = "writing"
                    except ValueError as error:
                        record["status"] = "held"
                        record["findings"] = list(dict.fromkeys([*record["findings"], str(error)]))
        if not changes:
            continue
        write = connection.execute(
            """INSERT INTO account_writes
            (tenant_id,run_id,file_id,source_id,path,before_sha256,after_sha256,content,changes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
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
        ).fetchone()
        bound = connection.execute(
            """SELECT d.id FROM desktop_source_bindings b JOIN desktop_devices d ON d.tenant_id=b.tenant_id AND d.id=b.device_id
            WHERE b.tenant_id=%s AND b.source_id=%s AND d.owner_id=%s AND d.revoked_at IS NULL AND d.expires_at>now()""",
            (run["tenant_id"], file["source_id"], run["actor_id"]),
        ).fetchone()
        if bound:
            from minkops_platform.desktop import enqueue_approved

            enqueue_approved(connection, run, bound["id"], "accounts.save", write["id"])


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
        current = connection.execute(
            "SELECT sha256 FROM account_files WHERE tenant_id=%s AND source_id=%s AND path=%s AND current",
            (tenant["id"], row["source_id"], row["path"]),
        ).fetchone()
        advance = current and current["sha256"] in (row["before_sha256"], row["after_sha256"])
        if not advance and not row["cancelled_at"]:
            raise ServiceError(
                "conflict",
                "The destination has a newer source version. Reconcile it before completing this write.",
            )
        if advance:
            connection.execute(
                "UPDATE account_files SET current=false WHERE tenant_id=%s AND source_id=%s AND path=%s",
                (tenant["id"], row["source_id"], row["path"]),
            )
            connection.execute(
                """INSERT INTO account_files (tenant_id,source_id,path,sha256,content)
                 VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,source_id,path,sha256) DO UPDATE SET current=true""",
                (tenant["id"], row["source_id"], row["path"], row["after_sha256"], content),
            )
        # A late cancelled receipt proves an earlier save, not that these are
        # today's bytes. Preserve newer observed source metadata and the audit.
        connection.execute(
            "UPDATE account_writes SET verified_at=now() WHERE tenant_id=%s AND id=%s",
            (tenant["id"], write_id),
        )
    pending = connection.execute(
        "SELECT count(*) AS n FROM account_writes WHERE tenant_id=%s AND run_id=%s AND verified_at IS NULL AND cancelled_at IS NULL",
        (tenant["id"], run_id),
    ).fetchone()["n"]
    if run["workflow_key"] == "bill-entry" and run.get("result"):
        result = run["result"]
        for change in row["changes"]:
            index = change.get("record_index")
            if index is not None:
                result["records"][index]["status"] = "saved"
        if run["state"] == "writing":
            from .tally_writes import complete_run

            complete_run(connection, run, result)
        else:
            connection.execute(
                "UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(result), run["id"])
            )
    elif not pending and run["state"] == "writing":
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
    connection.execute(
        "UPDATE account_tally_writes SET cancelled_at=now() WHERE tenant_id=%s AND run_id=%s AND finished_at IS NULL",
        (tenant["id"], run_id),
    )
    message = "Remaining saves cancelled. Inspect the destinations before refreshing discovery; already applied changes remain."
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
