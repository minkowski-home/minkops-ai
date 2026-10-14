"""Client-PC discovery catalogs. Local adapters observe; hosted Accounts proposes Excel meanings.

The catalog is a durable version, not a live claim about an offline source. A
partial scan is downloadable but cannot authorize a dependent workflow. The
existing Accounts catalog remains the write contract for MIN-119 Excel entries.
"""

import copy
import hashlib
import json
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from minkops_connectors.excel import open_workbook, schema_projection
from psycopg.types.json import Jsonb

from .accounts import service as accounts
from .accounts.catalog import validate_catalog
from .accounts.repository import files_for, public_run
from .errors import ServiceError
from .resources import REPOSITORY_ROOT
from .run_controls import observe_task, resolve_request, control_state, require_active


def latest_run(connection, tenant, user, device_id=None):
    """Scope discovery to an explicit, owned PC without falling back to another PC."""
    if device_id is not None:
        from .desktop import owned_device

        owned_device(connection, tenant["id"], user["id"], device_id)
    return connection.execute(
        """SELECT * FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s
        AND (%s::uuid IS NULL OR device_id=%s::uuid) ORDER BY created_at DESC LIMIT 1""",
        (tenant["id"], user["id"], device_id, device_id),
    ).fetchone()

CONFIG_SCHEMA = json.loads(
    (
        REPOSITORY_ROOT
        / "employees/accounts-desk/workflows/source-discovery/collection-config.schema.json"
    ).read_text()
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def workflow_context(connection, tenant_id, run_id, tools):
    """Pin a reviewed complete package, bounded to the consuming workflow's tools."""
    catalog = copy.deepcopy(require_ready(connection, tenant_id, run_id, tools))
    catalog["sources"] = [s for s in catalog["sources"] if s["tool"] in tools]
    catalog["master_lookup_version"] = "1"
    return catalog


def get_run(connection, tenant_id, run_id, lock=False):
    row = connection.execute(
        "SELECT * FROM discovery_runs WHERE tenant_id=%s AND id=%s"
        + (" FOR UPDATE" if lock else ""),
        (tenant_id, run_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Discovery run not found.")
    return row


def detail(connection, row, *, include_records=True):
    mapping = None
    if row["mapping_run_id"]:
        mapped = connection.execute(
            "SELECT * FROM account_runs WHERE tenant_id=%s AND id=%s",
            (row["tenant_id"], row["mapping_run_id"]),
        ).fetchone()
        mapping = public_run(connection, mapped)
    # Optional AI context analysis cannot hold back a complete native Tally
    # collection; Excel sources still need their analysed mappings.
    analysis_failed = bool(
        mapping and mapping["state"] == "failed" and row["catalog"]
        and not any(s["tool"] == "excel" for s in row["catalog"]["sources"])
    )
    state = row["state"]
    if state not in ("completed", "failed") and mapping:
        state = "review" if analysis_failed else mapping["state"]
    control = control_state(connection, row["tenant_id"], row["task_id"])
    if control != "active":
        state = control
    catalog = copy.deepcopy(row["catalog"])
    if catalog and mapping and mapping["result"]:
        catalog["excel_mappings"] = mapping["result"]
        catalog["context_notes"] = mapping["result"].get("context_notes", [])
    # Display a derived summary without rewriting the immutable native catalog.
    if catalog:
        from .accounts.client_context import master_lookup
        from .accounts.voucher_types import summary as voucher_summary

        for source in catalog.get("sources", []):
            if source["tool"] != "tally":
                continue
            for company in source.get("snapshot", {}).get("companies", []):
                if company.get("masters", {}).get("status") != "ready":
                    continue
                try:
                    lookup = master_lookup(company)
                    company["master_summary"] = lookup["summary"]
                    # Bill Entry offers these per company; records stay server-side.
                    company["purchase_voucher_types"] = voucher_summary(
                        [r["data"] for r in lookup["records"] if r["type"] == "VOUCHERTYPE"],
                        company.get("vouchers", {}).get("records", []),
                    )
                except ValueError as error:
                    company["master_lookup_error"] = str(error)
                    catalog["partial"] = True
        if not include_records:
            # Poll only review metadata. Full evidence remains in the immutable
            # catalog, downloads and execution context, never in growing DOMs.
            for source in catalog.get("sources", []):
                snapshot = source.get("snapshot", {})
                for company in snapshot.get("companies", []):
                    company.pop("identity", None)
                    for category in ("masters", "vouchers"):
                        company.get(category, {}).pop("records", None)
                for collection in snapshot.get("collections", []):
                    collection.pop("records", None)
            if mapping:
                mapping["config"] = {"file_provenance": mapping["config"].get("file_provenance", [])}
    return {
        **{
            k: row[k]
            for k in (
                "id",
                "task_id",
                "device_id",
                "config",
                "observations",
                "created_at",
                "confirmed_at",
            )
        },
        "state": state,
        "control_state": control,
        "catalog": catalog,
        "scope_changes": scope_changes(connection, row),
        "mapping_run": mapping,
        "analysis_failed": analysis_failed,
        "ready": state == "completed" and bool(row["confirmed_at"]) and not catalog["partial"]
        if catalog
        else False,
    }


def _tally_companies(catalog):
    return {c["company_guid"]: c["company"]
            for source in (catalog or {}).get("sources", []) if source["tool"] == "tally"
            for c in source.get("snapshot", {}).get("companies", []) if c.get("company_guid")}


def scope_changes(connection, row):
    """Companies added or no longer open since the confirmation before this run.

    Discovery reads only the companies open in Tally, so a smaller scope is a
    user's choice, shown at review rather than treated as missing evidence.
    Bill Entry can then route only to companies in the confirmed scope.
    """
    current = _tally_companies(row["catalog"])
    if not current:
        return None
    previous = connection.execute(
        """SELECT catalog FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s AND device_id=%s
        AND confirmed_at IS NOT NULL AND id<>%s AND created_at<%s ORDER BY created_at DESC LIMIT 1""",
        (row["tenant_id"], row["actor_id"], row["device_id"], row["id"], row["created_at"]),
    ).fetchone()
    if not previous:
        return None
    before = _tally_companies(previous["catalog"])
    listed = lambda guids, names: sorted(
        ({"company": names[g], "company_guid": g} for g in guids), key=lambda c: c["company"])
    return {"added": listed(current.keys() - before.keys(), current),
            "removed": listed(before.keys() - current.keys(), before)}


def _observe(connection, row, state, summary, progress):
    if control_state(connection, row["tenant_id"], row["task_id"]) == "stopped":
        return
    if state == 'failed':
        from .attention import audit, record
        item = record(connection,row,f"discovery:{row['id']}","Source discovery","Source unavailable")
        audit(connection,item,None,'failed',summary)
    observe_task(
        connection,
        tenant_id=row["tenant_id"],
        task_id=row["task_id"],
        run_id=row["id"],
        state=state,
        summary=summary,
        progress=progress,
        event_prefix="discovery",
    )


def launch(connection, tenant, user, body):
    from . import desktop

    try:
        Draft202012Validator(CONFIG_SCHEMA, format_checker=FormatChecker()).validate(body["config"])
    except ValidationError as error:
        raise ServiceError("invalid", "Choose valid Tally and Excel discovery options.") from error
    config = body["config"]
    if config["tally"]:
        from datetime import date

        tally = config["tally"]
        if set(tally) != {"port", "period"}:
            raise ServiceError(
                "invalid",
                "Discovery reads the companies open in Tally; specify only port and voucher period.",
            )
        start, end = map(date.fromisoformat, (tally["period"]["from"], tally["period"]["to"]))
        if start > end or (end - start).days > 3660:
            raise ServiceError("invalid", "Choose an ordered voucher period of at most ten years.")
    mode = config.get("destination_mode")
    observed_mode = (
        "both"
        if config["tally"] and config["excel_source_ids"]
        else ("tally" if config["tally"] else "excel")
    )
    if mode and mode != observed_mode:
        raise ServiceError(
            "invalid", "Select the sources required by the chosen Excel, Tally or Both option."
        )
    if not config["excel_source_ids"] and not config["tally"]:
        raise ServiceError("invalid", "Select at least one source.")
    fingerprint, previous = resolve_request(
        connection,
        tenant["id"],
        body["request_key"],
        body,
        lambda c, t, k: c.execute(
            "SELECT * FROM discovery_runs WHERE tenant_id=%s AND request_key=%s", (t, k)
        ).fetchone(),
    )
    if previous:
        return detail(connection, previous)
    device = desktop.owned_device(connection, tenant["id"], user["id"], body["device_id"])
    if config["tally"]:
        desktop.require_companion(device)
    workflow = connection.execute(
        "SELECT * FROM workflows WHERE tenant_id=%s AND key='source-discovery' AND status='active'",
        (tenant["id"],),
    ).fetchone()
    if not workflow:
        raise ServiceError("conflict", "Source discovery is not active in this workspace.")
    from .solution_policy import validate_option

    try:
        # The workspace's enabled tools bind the registered schema; enforce the
        # sources actually requested, not only the UI's displayed choice.
        validate_option(workflow["config_schema"], "destination_mode", observed_mode)
    except ValidationError as error:
        raise ServiceError("invalid", "This workspace does not use the selected source system.") from error
    for source_id in config["excel_source_ids"]:
        desktop._bound_source(connection, device, source_id)
    if (
        connection.execute(
            "SELECT count(*) AS n FROM desktop_jobs WHERE device_id=%s AND state IN ('queued','executing')",
            (device["id"],),
        ).fetchone()["n"]
        >= 10
    ):
        raise ServiceError("conflict", "Wait for this PC to finish its queued work.")
    task = connection.execute(
        "INSERT INTO tasks(tenant_id,workflow_id,title) VALUES(%s,%s,'Discover business sources') RETURNING id",
        (tenant["id"], workflow["id"]),
    ).fetchone()
    row = connection.execute(
        "INSERT INTO discovery_runs(tenant_id,actor_id,device_id,task_id,request_key,request_hash,config) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            tenant["id"],
            user["id"],
            device["id"],
            task["id"],
            body["request_key"],
            fingerprint,
            Jsonb(config),
        ),
    ).fetchone()
    job = connection.execute(
        "INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash) VALUES(%s,%s,%s,%s,'sources.discover',%s,%s,%s) RETURNING id",
        (
            tenant["id"],
            device["id"],
            user["id"],
            task["id"],
            Jsonb({"discovery_run_id": str(row["id"])}),
            uuid4(),
            fingerprint,
        ),
    ).fetchone()
    connection.execute("UPDATE discovery_runs SET job_id=%s WHERE id=%s", (job["id"], row["id"]))
    _observe(
        connection,
        row,
        "queued",
        f"Waiting for {device['name']}. Keep Minkops running on that PC.",
        0,
    )
    return detail(connection, row)


def plan(connection, device, job):
    row = get_run(connection, device["tenant_id"], job["input"]["discovery_run_id"])
    if (
        row["device_id"] != device["id"]
        or row["actor_id"] != device["owner_id"]
        or row["state"] not in ("queued", "executing")
    ):
        raise ServiceError("conflict", "This discovery is no longer collecting sources.")
    from . import desktop

    sources = [
        {"key": s, "tool": "excel", "label": desktop._bound_source(connection, device, s)["label"]}
        for s in row["config"]["excel_source_ids"]
    ]
    if row["config"]["tally"]:
        sources.append(
            {
                "key": "tally",
                "tool": "tally",
                "label": "Companies open in Tally",
            }
        )
    return {"config": row["config"], "sources": sources}


def progress(connection, device, job, body):
    row = get_run(connection, device["tenant_id"], job["input"]["discovery_run_id"], True)
    expected = {s["key"] for s in plan(connection, device, job)["sources"]}
    if body["source_key"] not in expected or body["status"] not in (
        "reading",
        "ready",
        "unavailable",
    ):
        raise ServiceError("invalid", "Invalid source observation.")
    observation = {
        "key": body["source_key"],
        "status": body["status"],
        "category": body.get("category"),
    }
    if observation["category"] and body["source_key"] != "tally":
        raise ServiceError("invalid", "Invalid discovery company.")
    measurement = body.get("progress")
    if measurement is not None:
        # Display telemetry is bounded and optional for older companions. It
        # never authorizes completion; only the validated receipt can do that.
        activities = {
            "Checking company", "Reading masters", "Collected masters",
            "Reading vouchers", "Collected vouchers", "Collected company",
            "Company needs attention", "Checking company scope",
            "Company scope checked", "Company scope needs attention",
            "Reading workbook", "Collected workbook", "Workbook needs attention",
        }
        if (
            not isinstance(measurement, dict)
            or set(measurement) - {"completed", "total", "activity", "item"}
            or type(measurement.get("completed")) is not int
            or type(measurement.get("total")) is not int
            or not 0 <= measurement["completed"] <= measurement["total"] <= 10000
            or measurement["total"] == 0
            or not isinstance(measurement.get("activity"), str)
            or measurement["activity"] not in activities
            or ("item" in measurement and (
                not isinstance(measurement["item"], str)
                or len(measurement["item"]) > 500
                or any(ord(char) < 32 for char in measurement["item"])
            ))
        ):
            raise ServiceError("invalid", "Invalid discovery progress.")
        observation["progress"] = measurement
    observations = [
        o
        for o in row["observations"]
        if (o["key"], o.get("category")) != (observation["key"], observation["category"])
    ] + [observation]
    connection.execute(
        "UPDATE discovery_runs SET state='executing',observations=%s,updated_at=now() WHERE id=%s",
        (Jsonb(observations), row["id"]),
    )
    connection.execute(
        "UPDATE desktop_jobs SET lease_until=now()+interval '2 minutes' WHERE id=%s", (job["id"],)
    )
    # Replace the latest measurement in durable state, without a task event
    # for every export chunk. Source/company state transitions stay auditable.
    previous = next((o for o in row["observations"] if
                     (o["key"], o.get("category")) ==
                     (observation["key"], observation["category"])), None)
    if previous is None or previous["status"] != observation["status"]:
        label = "Tally" if body["source_key"] == "tally" else "Excel folder"
        _observe(
            connection,
            row,
            "executing",
            f"{label}: "
            + {
                "reading": "Reading your selected source…",
                "ready": "Source collected.",
                "unavailable": "Needs attention; continuing with other sources.",
            }[body["status"]],
            30,
        )
    return {"observations": observations}


def _validate_tally(snapshot, config):
    from .accounts.client_context import validate_snapshot

    try:
        validate_snapshot(snapshot, config)
    except (ValueError, TypeError, KeyError) as error:
        raise ServiceError("invalid", str(error)) from error


def _fingerprint(excel_files, mappings, sources, config):
    """Fingerprint what confirmation authorizes, so an equal one reuses it.

    That is the source scope, Excel structure and approved meanings, and the
    configuration. Routine Tally data (vouchers and masters, including entries
    Minkops saved) is evidence collected under that authority, not a new decision.
    """
    return _digest({
        "excel": _structure(excel_files, mappings),
        "tally": [_tally_authority(s) for s in sources if s["tool"] == "tally"],
        "config": config,
    })


def _tally_authority(source):
    snapshot = source.get("snapshot") or {}
    if "company_scope" not in snapshot:
        return source  # Older single-company snapshots keep their full fingerprint.
    # Names are unique in a scope; open scopes may omit folder-local numbers.
    scope = sorted(snapshot["company_scope"], key=lambda c: c["company"])
    return {"key": source["key"], "company_scope": scope}


def _structure(files, mappings=None):
    """Stable layout signature: reference/transaction row additions do not change mappings."""
    layouts = []
    by_file = {m["file_id"]: [] for m in (mappings or {}).get("sheets", [])}
    for m in (mappings or {}).get("sheets", []):
        by_file[m["file_id"]].append(m)
    for f in files:
        w = open_workbook(bytes(f["content"]))
        sheets = []
        for s in w:
            selected = [m for m in by_file.get(str(f["id"]), []) if m["sheet"] == s.title]
            header_rows = (
                {m["header_row"] for m in selected}
                or {
                    int(t.ref.split(":")[0].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
                    for t in s.tables.values()
                }
                or set(range(1, min(s.max_row, 10) + 1))
            )
            sheets.append(
                {
                    "sheet": s.title,
                    "columns": s.max_column,
                    "formulas": [
                        {"cell": cell.coordinate, "formula": cell.value}
                        for cell in s._cells.values()
                        if cell.data_type == "f"
                    ],
                    "tables": [
                        {
                            "name": t.name,
                            "start": t.ref.split(":")[0],
                            "end_column": "".join(c for c in t.ref.split(":")[-1] if c.isalpha()),
                            "columns": [c.name for c in t.tableColumns],
                        }
                        for t in s.tables.values()
                    ],
                    "headers": [
                        {"row": r, "values": [str(c.value or "") for c in s[r]]}
                        for r in sorted(header_rows)
                    ],
                }
            )
        layouts.append({"source_id": str(f["source_id"]), "path": f["path"], "sheets": sheets})
    return sorted(layouts, key=lambda f: (f["source_id"], f["path"]))


def collect(connection, device, job, result):
    """Atomic receipt: validate all scope before persisting a catalog or launching hosted mappings."""
    from . import desktop

    row = get_run(connection, device["tenant_id"], job["input"]["discovery_run_id"], True)
    planned = plan(connection, device, job)
    if (
        not isinstance(result, dict)
        or set(result) != {"sources"}
        or not isinstance(result["sources"], list)
    ):
        raise ServiceError("invalid", "Invalid discovery receipt.")
    expected = {s["key"]: s for s in planned["sources"]}
    received = result["sources"]
    if (
        len(received) != len(expected)
        or any(not isinstance(s, dict) for s in received)
        or {s.get("key") for s in received} != set(expected)
    ):
        raise ServiceError("invalid", "Discovery results do not match the approved sources.")
    catalog_sources = []
    excel_files = []
    partial = False
    for source in received:
        if source.get("tool") != expected[source["key"]]["tool"] or source.get("status") not in (
            "ready",
            "unavailable",
        ):
            raise ServiceError("invalid", "Invalid discovered source.")
        if source["status"] == "unavailable":
            if (
                set(source) != {"key", "tool", "status", "error"}
                or not isinstance(source["error"], str)
                or not 1 <= len(source["error"]) <= 300
            ):
                raise ServiceError("invalid", "Invalid source error.")
            partial = True
            catalog_sources.append(source)
            continue
        if source["tool"] == "tally":
            if set(source) != {"key", "tool", "status", "snapshot"}:
                raise ServiceError("invalid", "Invalid Tally snapshot.")
            _validate_tally(
                source["snapshot"], {**row["config"]["tally"], "depth": row["config"]["depth"]}
            )
            partial |= source["snapshot"]["partial"]
            catalog_sources.append(source)
        else:
            if (
                set(source) != {"key", "tool", "status", "files", "workbooks"}
                or not isinstance(source["files"], list)
                or not 1 <= len(source["files"]) <= 100
                or not isinstance(source["workbooks"], list)
            ):
                raise ServiceError("invalid", "Invalid Excel folder snapshot.")
            bound = desktop._bound_source(connection, device, source["key"])
            names = []
            contents = []
            for f in source["files"]:
                if (
                    not isinstance(f, dict)
                    or set(f) != {"path", "content"}
                    or not isinstance(f["path"], str)
                ):
                    raise ServiceError("invalid", "Invalid folder file.")
                names.append(f["path"])
                contents.append(desktop._bytes(f["content"]))
            if sum(map(len, contents)) > 30_000_000:
                raise ServiceError("invalid", "Folder snapshot exceeds 30 MB.")
            books = source["workbooks"]
            originals = {
                n: b for n, b in zip(names, contents, strict=True) if n.lower().endswith(".xlsx")
            }
            if (
                not originals
                or len(books) != len(originals)
                or any(not isinstance(b, dict) for b in books)
                or {b.get("path") for b in books} != set(originals)
            ):
                raise ServiceError("invalid", "Excel discovery omitted a selected workbook.")
            for book in books:
                if book.get("sha256") != hashlib.sha256(
                    originals[book["path"]]
                ).hexdigest() or book.get("status") not in ("ready", "unavailable"):
                    raise ServiceError("invalid", "Workbook changed during discovery.")
                if book["status"] == "unavailable" and (
                    set(book) != {"path", "sha256", "status", "error"}
                    or not isinstance(book["error"], str)
                    or not 1 <= len(book["error"]) <= 300
                ):
                    raise ServiceError("invalid", "Invalid workbook error.")
                if book["status"] == "ready" and set(book) != {
                    "path",
                    "sha256",
                    "status",
                    "structure",
                }:
                    raise ServiceError("invalid", "Invalid workbook structure.")
                if book["status"] == "ready":
                    try:
                        content, structure = schema_projection(
                            originals[book["path"]], book["structure"]
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        raise ServiceError(
                            "invalid", "Discovery must contain schema and headers only."
                        ) from error
                    originals[book["path"]] = content
                    book["sha256"] = hashlib.sha256(content).hexdigest()
                    book["structure"] = structure
            good = [b["path"] for b in books if b["status"] == "ready"]
            current = {}
            if good:
                uploaded = accounts.upload_source(
                    connection,
                    {"id": row["tenant_id"]},
                    {"id": row["actor_id"], "is_platform_admin": False},
                    good,
                    [originals[n] for n in good],
                    bound["label"],
                    True,
                    bound["id"],
                    refresh_extensions=[".xlsx"],
                    schema_only=True,
                )
                current = {
                    f["path"]: f
                    for f in files_for(
                        connection, row["tenant_id"], [str(f["id"]) for f in uploaded["files"]]
                    )
                }
            for book in books:
                if book["status"] == "ready":
                    f = current[book["path"]]
                    try:
                        w = open_workbook(bytes(f["content"]))
                        local = book["structure"]["sheets"]
                        if [s["sheet"] for s in local] != w.sheetnames:
                            raise ValueError("Missing sheet")
                        for observed, actual in zip(local, w, strict=True):
                            if {t["name"]: t["range"] for t in observed["tables"]} != {
                                t.name: t.ref for t in actual.tables.values()
                            }:
                                raise ValueError("Missing table")
                    except (KeyError, TypeError, ValueError) as error:
                        raise ServiceError(
                            "invalid", "Local Excel structure does not match its workbook snapshot."
                        ) from error
                    excel_files.append(f)
                    book["file_id"] = str(f["id"])
                else:
                    partial = True
            catalog_sources.append(
                {
                    "key": source["key"],
                    "tool": "excel",
                    "status": "ready",
                    "label": bound["label"],
                    "workbooks": books,
                }
            )
    if len(excel_files) > 45 or sum(len(f["content"]) for f in excel_files) > 8_000_000:
        raise ServiceError("invalid", "Choose up to 45 workbooks and 8 MB for discovery.")
    config = row["config"]
    previous = connection.execute(
        "SELECT * FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s AND device_id=%s AND config=%s AND confirmed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1",
        (row["tenant_id"], row["actor_id"], row["device_id"], Jsonb(config)),
    ).fetchone()
    previous_maps = previous["catalog"].get("excel_mappings") if previous else None
    # Match current file versions to prior mappings by source + path, never by filename alone.
    remapped = copy.deepcopy(previous_maps)
    if remapped:
        old = {
            b["file_id"]: (s["key"], b["path"])
            for s in previous["catalog"]["sources"]
            if s["tool"] == "excel"
            for b in s["workbooks"]
        }
        new = {(str(f["source_id"]), f["path"]): str(f["id"]) for f in excel_files}
        for m in remapped["sheets"]:
            m["file_id"] = new.get(old.get(m["file_id"]), m["file_id"])
    signature = _fingerprint(excel_files, remapped, catalog_sources, config)
    unchanged = previous and not partial and previous["fingerprint"] == signature
    if unchanged and previous["catalog"].get("context_notes"):
        from .accounts.client_context import validate_notes

        try:
            validate_notes(previous["catalog"]["context_notes"], {"sources": catalog_sources})
        except ValueError:
            # A confirmed note cites evidence that is no longer collected.
            unchanged = False
    from .accounts.client_context import CONTEXT_RECORD_FORMAT

    catalog = {
        "master_lookup_version": "1",
        "context_record_format": CONTEXT_RECORD_FORMAT,
        "format_version": "2",
        "context_notes": copy.deepcopy(previous["catalog"].get("context_notes", []))
        if unchanged
        else [],
        "collected_at": connection.execute("SELECT now() AS time").fetchone()["time"].isoformat(),
        "run_id": str(row["id"]),
        "device_id": str(row["device_id"]),
        "depth": config["depth"],
        "sources": catalog_sources,
        "partial": partial,
        "review": {
            "status": "confirmed" if unchanged else "required",
            "reused_from": str(previous["id"]) if unchanged else None,
        },
        "excel_mappings": remapped if unchanged else None,
    }
    if not partial:
        from .accounts.client_context import context_assets

        try:
            assets, _ = context_assets(catalog)
            if (
                len(assets) + len(excel_files) > 45
                or sum(len(f["content"]) for f in assets + excel_files) > 8_000_000
            ):
                raise ValueError("Complete collection exceeds hosted interpretation limits.")
        except ValueError:
            partial = catalog["partial"] = True
            catalog["context_error"] = (
                "Complete collection exceeds hosted interpretation limits. Reduce the voucher period or hand off; masters cannot be sampled."
            )
            unchanged = False
            catalog["review"].update(status="required", reused_from=None)
    if partial:
        from .attention import record
        record(connection,row,f"discovery:{row['id']}","Source discovery","Incomplete discovery")
    state = "completed" if unchanged else "review"
    mapping_id = None
    if unchanged and remapped:
        validate_catalog(remapped, {str(f["id"]): bytes(f["content"]) for f in excel_files})
        linked = connection.execute(
            "INSERT INTO account_catalogs(tenant_id,actor_id,definition_version,catalog) VALUES(%s,%s,%s,%s) RETURNING id",
            (row["tenant_id"], row["actor_id"], "0.4.0", Jsonb(remapped)),
        ).fetchone()
        catalog["excel_catalog_id"] = str(linked["id"])
    elif config.get("ai_context", True) and not partial and control_state(connection, row["tenant_id"], row["task_id"]) != "stopped":
        connection.execute(
            "UPDATE discovery_runs SET catalog=%s WHERE id=%s", (Jsonb(catalog), row["id"])
        )
        mapped = accounts.launch_run(
            connection,
            {"id": row["tenant_id"]},
            {"id": row["actor_id"]},
            {
                "key": "source-discovery",
                "request_key": str(uuid4()),
                "file_ids": [str(f["id"]) for f in excel_files],
                "catalog_id": None,
                "config": {"discovery_run_id": str(row["id"])},
            },
            task_id=row["task_id"],
        )
        mapping_id = mapped["id"]
        state = "queued"
        connection.execute(
            "UPDATE account_runs SET config=config || %s WHERE id=%s",
            (Jsonb({"local_discovery_snapshot": catalog}), mapping_id),
        )
    updated = connection.execute(
        "UPDATE discovery_runs SET catalog=%s,observations=%s,state=%s,fingerprint=%s,mapping_run_id=%s,confirmed_at=CASE WHEN %s THEN now() ELSE NULL END,updated_at=now() WHERE id=%s RETURNING *",
        (
            Jsonb(catalog),
            Jsonb([{"key": s["key"], "status": s["status"]} for s in catalog_sources]),
            state,
            signature,
            mapping_id,
            bool(unchanged),
            row["id"],
        ),
    ).fetchone()
    if not mapping_id:
        _observe(
            connection,
            updated,
            state,
            "Sources refreshed. Confirmed mappings retained."
            if unchanged
            else "Review the collected sources."
            + (" Some sources need attention." if partial else ""),
            100 if unchanged else 70,
        )
    return {
        "discovery_run_id": str(row["id"]),
        "partial": partial,
        "source_count": len(catalog_sources),
    }


def fail(connection, device, job, error):
    row = get_run(connection, device["tenant_id"], job["input"]["discovery_run_id"], True)
    connection.execute(
        "UPDATE discovery_runs SET state='failed',updated_at=now() WHERE id=%s", (row["id"],)
    )
    _observe(connection, row, "failed", error, 30)


def confirm(connection, tenant, user, run_id, body):
    row = get_run(connection, tenant["id"], run_id, True)
    require_active(connection, tenant["id"], row["task_id"])
    if row["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Only the operator who ran discovery can confirm it.")
    current = detail(connection, row)
    if current["state"] == "completed":
        return current
    if current["state"] != "review" or not current["catalog"] or current["catalog"]["partial"]:
        raise ServiceError(
            "conflict",
            "Finish all selected sources before confirming. Partial results remain available to review and download.",
        )
    # detail() is a presentation projection with derived master summaries.
    # Persist native evidence, then apply approved mappings explicitly; display
    # fields must never change source fingerprints or invalidate review reuse.
    catalog = copy.deepcopy(row["catalog"])
    if current["analysis_failed"]:
        catalog["context_notes"] = []
        _close_failed_analysis(connection, row, user)
    elif row["mapping_run_id"]:
        mappings = body.get("excel_mappings") or current["mapping_run"]["result"]
        approved = accounts.approve_run(
            connection,
            tenant,
            user,
            row["mapping_run_id"],
            {"result": mappings, "acknowledge_findings": False},
            require_destination=False,
        )
        catalog["excel_catalog_id"] = str(approved["catalog_id"])
        catalog["excel_mappings"] = mappings
        from .accounts.client_context import validate_notes

        catalog["context_notes"] = validate_notes(mappings.get("context_notes", []), catalog)
    files = files_for(
        connection,
        tenant["id"],
        [
            b["file_id"]
            for s in catalog["sources"]
            if s["tool"] == "excel"
            for b in s["workbooks"]
            if b["status"] == "ready"
        ],
    )
    catalog["review"]["status"] = "confirmed"
    signature = _fingerprint(files, catalog.get("excel_mappings"), catalog["sources"], row["config"])
    updated = connection.execute(
        "UPDATE discovery_runs SET state='completed',catalog=%s,fingerprint=%s,confirmed_at=now(),updated_at=now() WHERE id=%s RETURNING *",
        (Jsonb(catalog), signature, row["id"]),
    ).fetchone()
    _observe(
        connection,
        row,
        "completed",
        "Source catalog confirmed and available for your workflows.",
        100,
    )
    return detail(connection, updated)


def _close_failed_analysis(connection, row, user):
    """Confirming without context notes settles the failed analysis's attention."""
    from .attention import audit

    item = connection.execute(
        "SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s AND status='pending' FOR UPDATE",
        (row["tenant_id"], f"run:{row['mapping_run_id']}"),
    ).fetchone()
    if item:
        connection.execute(
            "UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
            (user["id"], item["id"]),
        )
        audit(connection, item, user["id"], "confirmed_without_analysis",
              "Tally sources confirmed without AI context notes.")


def require_ready(connection, tenant_id, run_id, required_tools):
    """Shared dependent-workflow gate for the catalog's explicit required sources.

    MIN-119/120 can pin this returned version and recheck live source versions
    before writing; discovery confirmation alone never grants a write.
    """
    row = get_run(connection, tenant_id, run_id)
    current = detail(connection, row)
    tools = {s["tool"] for s in (current["catalog"] or {}).get("sources", [])}
    if not current["ready"] or not set(required_tools).issubset(tools):
        raise ServiceError(
            "conflict",
            "Required sources are incomplete or unconfirmed. Finish source discovery first.",
        )
    latest = connection.execute(
        "SELECT * FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s AND device_id=%s AND config=%s ORDER BY created_at DESC LIMIT 1",
        (tenant_id, row["actor_id"], row["device_id"], Jsonb(row["config"])),
    ).fetchone()
    # An unchanged confirmed refresh preserves pinned approvals. Pending,
    # partial or changed observations still block use of the older package.
    if latest["id"] != row["id"] and (
        not detail(connection, latest)["ready"] or latest["fingerprint"] != row["fingerprint"]
    ):
        if latest["state"] in ("queued", "executing"):
            raise ServiceError(
                "conflict",
                "A newer Source discovery is still collecting. Wait for it to finish, then start again.",
            )
        raise ServiceError(
            "conflict", "Source discovery has a newer run. Review the latest catalog first."
        )
    return current["catalog"]
