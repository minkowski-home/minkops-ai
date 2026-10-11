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
from .run_controls import observe_task, resolve_request

CATEGORIES = [
    "company",
    "groups",
    "ledgers",
    "voucher_types",
    "stock_items",
    "stock_groups",
    "units",
    "godowns",
    "cost_centres",
    "cost_categories",
    "currencies",
]
CONFIG_SCHEMA = json.loads(
    (
        REPOSITORY_ROOT
        / "employees/accounts-desk/workflows/source-discovery/collection-config.schema.json"
    ).read_text()
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def workflow_context(connection, tenant_id, run_id, tools, *, tally_categories=None):
    """Pin reviewed schema context, bounded to a dependent workflow's tool scope.

    Every client owns its catalog; core skills never read a global client schema.
    Full client-context packages retain their native records for lookup.
    """
    catalog = copy.deepcopy(require_ready(connection, tenant_id, run_id, tools))
    catalog["sources"] = [s for s in catalog["sources"] if s["tool"] in tools]
    for source in catalog["sources"]:
        if source["tool"] != "tally":
            continue
        snapshot = source["snapshot"]
        if "companies" in snapshot:
            continue
        categories = set(tally_categories or CATEGORIES)
        if not categories <= set(CATEGORIES):
            raise ValueError("Unsupported Tally schema context.")
        snapshot["collections"] = [
            c for c in snapshot["collections"] if c["category"] in categories
        ]
        for collection in snapshot["collections"]:
            collection["records"] = []
            collection["count"] = 0
        if "schema_tables" in snapshot and tally_categories is not None:
            names = {c["schema"]["table"] for c in snapshot["collections"] if "schema" in c}
            snapshot["schema_tables"] = [
                t for t in snapshot["schema_tables"] if t["table"] in names
            ]
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


def detail(connection, row):
    mapping = None
    if row["mapping_run_id"]:
        mapped = connection.execute(
            "SELECT * FROM account_runs WHERE tenant_id=%s AND id=%s",
            (row["tenant_id"], row["mapping_run_id"]),
        ).fetchone()
        mapping = public_run(connection, mapped)
    state = row["state"]
    if state not in ("completed", "failed") and mapping:
        state = mapping["state"]
    catalog = copy.deepcopy(row["catalog"])
    if catalog and mapping and mapping["result"]:
        catalog["excel_mappings"] = mapping["result"]
        catalog["context_notes"] = mapping["result"].get("context_notes", [])
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
        "catalog": catalog,
        "mapping_run": mapping,
        "ready": state == "completed" and bool(row["confirmed_at"]) and not catalog["partial"]
        if catalog
        else False,
    }


def _observe(connection, row, state, summary, progress):
    if state == 'failed':
        from .attention import record, audit
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
    if config["depth"] not in ("structure", "client_context"):
        raise ServiceError(
            "invalid",
            "Choose structure or complete client context discovery.",
        )
    if config["depth"] == "client_context" and config["tally"]:
        from datetime import date

        tally = config["tally"]
        if set(tally) != {"port", "period"}:
            raise ServiceError(
                "invalid",
                "Complete discovery reads all loaded companies; specify only port and voucher period.",
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
    workflow = connection.execute(
        "SELECT * FROM workflows WHERE tenant_id=%s AND key='source-discovery' AND status='active'",
        (tenant["id"],),
    ).fetchone()
    if not workflow:
        raise ServiceError("conflict", "Source discovery is not active in this workspace.")
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
                "label": row["config"]["tally"].get("company", "All loaded companies"),
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
    if observation["category"] and (
        body["source_key"] != "tally"
        or (
            row["config"]["depth"] != "client_context"
            and observation["category"] not in row["config"]["tally"]["categories"]
        )
    ):
        raise ServiceError("invalid", "Invalid discovery category.")
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
    if observations != row["observations"]:
        label = "Tally" if body["source_key"] == "tally" else "Excel folder"
        _observe(
            connection,
            row,
            "executing",
            f"{label}: "
            + {
                "reading": "Reading your selected sourceâ€¦",
                "ready": "Source collected.",
                "unavailable": "Needs attention; continuing with other sources.",
            }[body["status"]],
            30,
        )
    return {"observations": observations}


def _validate_tally(snapshot, config):
    if config["depth"] == "client_context":
        from .accounts.client_context import validate_snapshot

        try:
            validate_snapshot(snapshot, config)
        except (ValueError, TypeError, KeyError) as error:
            raise ServiceError("invalid", str(error)) from error
        return
    if (
        not isinstance(snapshot, dict)
        or set(snapshot)
        != (
            {"company", "port", "collections", "schema_tables"}
            if config["depth"] == "structure"
            else {"company", "port", "collections"}
        )
        or snapshot["company"] != config["company"]
        or snapshot["port"] != config["port"]
        or not isinstance(snapshot["collections"], list)
    ):
        raise ServiceError("invalid", "Tally returned a different company or scope.")
    if config["depth"] == "structure":
        tables = snapshot["schema_tables"]
        if not isinstance(tables, list) or len(tables) > 500:
            raise ServiceError("invalid", "Invalid Tally metadata scope.")
        names = []
        for table in tables:
            if (
                not isinstance(table, dict)
                or set(table) != {"table", "columns"}
                or not isinstance(table["table"], str)
                or not 1 <= len(table["table"]) <= 200
            ):
                raise ServiceError("invalid", "Invalid Tally metadata table.")
            names.append(table["table"])
            _validate_columns(table["columns"])
        if len(names) != len(set(names)):
            raise ServiceError("invalid", "Duplicate Tally metadata tables.")
        if sum(len(t["columns"]) for t in tables) > 100000:
            raise ServiceError("invalid", "Tally metadata exceeds the supported scope.")
    seen = []
    for c in snapshot["collections"]:
        if not isinstance(c, dict) or c.get("status") not in ("ready", "unavailable"):
            raise ServiceError("invalid", "Invalid Tally collection.")
        seen.append(c.get("category"))
        if c["status"] == "ready":
            if (
                set(c)
                != (
                    {"category", "status", "count", "fields", "records", "schema"}
                    if config["depth"] == "structure"
                    else {"category", "status", "count", "fields", "records"}
                )
                or type(c["count"]) is not int
                or not 0 <= c["count"] <= 10000
                or not isinstance(c["fields"], list)
                or any(not isinstance(f, str) for f in c["fields"])
                or not isinstance(c["records"], list)
                or any(not isinstance(r, dict) for r in c["records"])
                or len(c["records"]) != (0 if config["depth"] == "structure" else c["count"])
            ):
                raise ServiceError("invalid", "Invalid Tally reference records.")
            if config["depth"] == "structure":
                schema = c["schema"]
                if (
                    c["count"] != 0
                    or not isinstance(schema, dict)
                    or set(schema) != {"source", "coverage", "table", "columns"}
                    or schema["source"] != "odbc_metadata"
                    or schema["coverage"] not in ("exposed_top_level_methods", "not_exposed")
                    or not isinstance(schema["table"], str)
                ):
                    raise ServiceError("invalid", "Structure discovery cannot include records.")
                _validate_columns(schema["columns"])
                if c["fields"] != [col["name"] for col in schema["columns"]] or schema[
                    "columns"
                ] != next(
                    (t["columns"] for t in tables if t["table"].lower() == schema["table"].lower()),
                    [],
                ):
                    raise ServiceError(
                        "invalid", "Tally metadata fields do not match the observed table."
                    )
        elif (
            set(c) != {"category", "status", "error"}
            or not isinstance(c["error"], str)
            or not 1 <= len(c["error"]) <= 300
        ):
            raise ServiceError("invalid", "Invalid Tally collection error.")
    if len(seen) != len(set(seen)) or set(seen) != set(config["categories"]):
        raise ServiceError("invalid", "Tally discovery omitted selected categories.")


def _validate_columns(columns):
    if (
        not isinstance(columns, list)
        or len(columns) > 2000
        or any(
            not isinstance(c, dict)
            or set(c) != {"name", "type", "nullable", "ordinal"}
            or not isinstance(c["name"], str)
            or not 1 <= len(c["name"]) <= 300
            or not isinstance(c["type"], str)
            or len(c["type"]) > 100
            or type(c["nullable"]) is not bool
            or type(c["ordinal"]) is not int
            or c["ordinal"] < 0
            for c in columns
        )
    ):
        raise ServiceError("invalid", "Invalid Tally column metadata.")
    # Tally exposes repeated method names at distinct ODBC positions (e.g.
    # $Category in CostCentreBreakUp). Preserve that schema; the position is
    # the column identity. Repeated positions still indicate an invalid receipt.
    if len({c["ordinal"] for c in columns}) != len(columns):
        raise ServiceError("invalid", "Duplicate Tally metadata columns.")


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
            partial |= source["snapshot"].get("partial", False) or any(
                c["status"] != "ready" for c in source["snapshot"].get("collections", [])
            )
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
                if book["status"] == "ready" and row["config"]["depth"] in (
                    "structure",
                    "client_context",
                ):
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
                    schema_only=row["config"]["depth"] in ("structure", "client_context"),
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
    signature = _digest(
        {
            "excel": _structure(excel_files, remapped),
            "tally": [s for s in catalog_sources if s["tool"] == "tally"],
            "config": config,
        }
    )
    unchanged = previous and not partial and previous["fingerprint"] == signature
    catalog = {
        "format_version": "2" if config["depth"] == "client_context" else "1",
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
    if config["depth"] == "client_context" and not partial:
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
    elif (excel_files or config["depth"] == "client_context") and not partial:
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
                "config": {"discovery_depth": "structure", "discovery_run_id": str(row["id"])},
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
    catalog = current["catalog"]
    if row["mapping_run_id"]:
        mappings = body.get("excel_mappings") or current["mapping_run"]["result"]
        approved = accounts.approve_run(
            connection,
            tenant,
            user,
            row["mapping_run_id"],
            {"result": mappings, "acknowledge_findings": False},
            require_destination=row["config"]["depth"] == "business_mappings",
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
    signature = _digest(
        {
            "excel": _structure(files, catalog.get("excel_mappings")),
            "tally": [s for s in catalog["sources"] if s["tool"] == "tally"],
            "config": row["config"],
        }
    )
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
    if latest["id"] != row["id"]:
        # Periodic discovery must not invalidate an in-flight approval when its
        # confirmed structure and references are exactly unchanged. Keep the
        # pinned catalog; pending, partial or changed observations still block.
        if not detail(connection, latest)["ready"] or latest["fingerprint"] != row["fingerprint"]:
            raise ServiceError(
                "conflict", "Source discovery has a newer run. Review the latest catalog first."
            )
    return current["catalog"]
