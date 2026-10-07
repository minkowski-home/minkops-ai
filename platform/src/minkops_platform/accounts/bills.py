"""Bill identity and destination reconciliation independent of model decisions.

Identity is business-derived, never a run UUID or upload filename. Destination
keys remain authoritative for backfills and externally created records.
"""

import hashlib
import json
from uuid import uuid4
from datetime import date
from decimal import Decimal, InvalidOperation

from minkops_platform.errors import ServiceError
from psycopg.types.json import Jsonb


def normalized(value):
    return str(value).strip().casefold()


def business_identity(data):
    vendor, invoice = data.get("vendor"), data.get("invoice_number")
    if (
        not isinstance(vendor, str)
        or not vendor.strip()
        or not isinstance(invoice, str)
        or not invoice.strip()
    ):
        raise ValueError("Supplier and invoice number are required for bill identity.")
    issued = date.fromisoformat(str(data.get("date")))
    year = issued.year if issued.month >= 4 else issued.year - 1
    return hashlib.sha256(
        json.dumps([normalized(vendor), normalized(invoice), year]).encode()
    ).hexdigest()


def excel_matches(data, mapping, rows):
    keys = mapping["key_columns"]
    if not keys or any(data.get(k) in (None, "") for k in keys):
        raise ValueError("Complete confirmed business keys are required.")
    concepts = {c.get("concept"): c["name"] for c in mapping["columns"] if c.get("concept")}
    identity_fields = ("vendor", "invoice_number", "date")
    if all(k in concepts for k in identity_fields):
        identity = business_identity({k: data.get(concepts[k]) for k in identity_fields})
        matches = []
        for row in rows:
            candidate = row["data"]
            try:
                existing = {k: candidate.get(concepts[k]) for k in identity_fields}
                existing["date"] = str(existing["date"]).split("T")[0]
                if business_identity(existing) == identity:
                    matches.append(candidate)
            except ValueError:
                if all(
                    normalized(candidate.get(concepts[k])) == normalized(data.get(concepts[k]))
                    for k in ("vendor", "invoice_number")
                ):
                    raise ValueError(
                        "Existing bill has incomplete identity. Review the destination first."
                    ) from None
    else:
        matches = [
            r["data"]
            for r in rows
            if all(normalized(r["data"].get(k)) == normalized(data[k]) for k in keys)
        ]
    return matches


def classify_excel(data, mapping, rows):
    matches = excel_matches(data, mapping, rows)
    if len(matches) > 1:
        return "ambiguous"
    if not matches:
        return "new"
    # App IDs are provenance, not user-observed invoice values. Formula columns
    # without a business concept are excluded from business equality.
    names = [
        c["name"]
        for c in mapping["columns"]
        if c.get("concept") != "entry_id" and data.get(c["name"]) is not None
    ]
    return (
        "duplicate"
        if all(same_value(matches[0].get(k), data.get(k)) for k in names)
        else "correction"
    )


def same_value(left, right):
    if type(left) in (int, float) and type(right) in (int, float):
        return Decimal(str(left)) == Decimal(str(right))
    return normalized(left) == normalized(right)


def capture_excel_state(result, catalog, contents):
    from minkops_connectors.excel import sheet_records

    mappings = {
        (s["file_id"], s["sheet"], s.get("table")): s
        for s in catalog["sheets"]
        if s["role"] == "destination"
    }
    for record in result["records"]:
        mapping = mappings[(record["destination_file_id"], record["sheet"], record.get("table"))]
        try:
            matches = excel_matches(
                record["data"], mapping, sheet_records(contents[mapping["file_id"]], mapping)
            )
            record["expected_excel"] = matches[0] if len(matches) == 1 else None
        except ValueError:
            record["expected_excel"] = None
    return result


TALLY_COLUMNS = [
    ("invoice_number", "string", True),
    ("vendor", "string", True),
    ("date", "string", True),
    ("purchase_ledger", "string", True),
    ("subtotal", "number", True),
    ("tax", "number", True),
    ("tax_ledger", "string", False),
    ("total", "number", True),
    ("cost_code", "string", False),
]


def tally_mapping(catalog_id):
    return {
        "sheets": [
            {
                "file_id": str(catalog_id),
                "sheet": "Purchase",
                "table": None,
                "role": "destination",
                "header_row": 1,
                "key_columns": ["vendor", "invoice_number", "date"],
                "columns": [
                    {"name": name, "concept": name, "type": kind, "required": required}
                    for name, kind, required in TALLY_COLUMNS
                ],
            }
        ]
    }


def tally_target(connection, tenant, user, discovery_id):
    from minkops_platform import desktop, discovery

    catalog = discovery.require_ready(connection, tenant["id"], discovery_id, ["tally"])
    row = discovery.get_run(connection, tenant["id"], discovery_id)
    if row["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Use source discovery confirmed by your account.")
    desktop.owned_device(connection, tenant["id"], user["id"], row["device_id"])
    source = next(s["snapshot"] for s in catalog["sources"] if s["tool"] == "tally")
    if "schema_tables" in source:
        # Metadata is reusable context, not a supplier directory. Bill Entry
        # collects its own bounded references through the registered PC.
        return {
            "device_id": str(row["device_id"]),
            "company": source["company"],
            "port": source["port"],
            "discovery_id": str(discovery_id),
            "schema_only": True,
        }
    return target_from_references(source, row["device_id"], discovery_id)


def target_from_references(source, device_id, discovery_id):
    required = {"company", "ledgers", "voucher_types"}
    collections = {c["category"]: c for c in source["collections"]}
    if any(k not in collections or collections[k]["status"] != "ready" for k in required):
        raise ServiceError(
            "conflict", "Discover company, ledgers and voucher types before bill entry."
        )

    def name(record):
        value = record.get("@_NAME", record.get("NAME"))
        return value.get("#text") if isinstance(value, dict) else value

    ledgers = [name(r) for r in collections["ledgers"]["records"]]
    companies = collections["company"]["records"]
    if len(companies) != 1:
        raise ServiceError("conflict", "Discover exactly one selected company before bill entry.")
    company_guid = companies[0].get("GUID")
    if company_guid is not None and (not isinstance(company_guid, str) or not company_guid.strip()):
        raise ServiceError("conflict", "Refresh the company's observed identity before bill entry.")
    ledger_versions = {
        name(r): {k: r.get(k) for k in ("GUID", "PARENT", "ALTERID")}
        for r in collections["ledgers"]["records"]
    }
    voucher_types = [name(r) for r in collections["voucher_types"]["records"]]
    if "Purchase" not in voucher_types:
        raise ServiceError(
            "conflict", "A Purchase voucher type is required in the selected company."
        )
    return {
        "device_id": str(device_id),
        "company": source["company"],
        "destination_key": f"company:{company_guid}"
        if company_guid
        else f"device:{device_id}:{source['company']}",
        "port": source["port"],
        "ledgers": ledgers,
        "discovery_id": str(discovery_id),
        "references": {"company_guid": company_guid, "ledgers": ledger_versions},
    }


def queue_tally_context(connection, run):
    target = run["config"]["tally_target"]
    job = connection.execute(
        """INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
        VALUES (%s,%s,%s,%s,'tally.references',%s,%s,%s) RETURNING id""",
        (
            run["tenant_id"],
            target["device_id"],
            run["actor_id"],
            run["task_id"],
            Jsonb({"run_id": str(run["id"])}),
            uuid4(),
            str(run["request_hash"]),
        ),
    ).fetchone()
    connection.execute(
        "UPDATE workflow_runs SET config=config || %s WHERE id=%s",
        (Jsonb({"tally_context_job_id": str(job["id"])}), run["id"]),
    )


def context_plan(connection, device, job):
    from .repository import run_for

    run = run_for(connection, device["tenant_id"], job["input"]["run_id"])
    target = run["config"]["tally_target"]
    if (
        str(target["device_id"]) != str(device["id"])
        or run["actor_id"] != device["owner_id"]
        or run["state"] != "queued"
    ):
        raise ServiceError("conflict", "This workflow is no longer preparing its source context.")
    tally_target(
        connection, {"id": device["tenant_id"]}, {"id": device["owner_id"]}, target["discovery_id"]
    )
    return {
        "company": target["company"],
        "port": target["port"],
        "categories": ["company", "ledgers", "voucher_types"],
        "depth": "reference_data",
    }


def accept_context(connection, device, job, result):
    from minkops_platform.discovery import _validate_tally
    from .repository import run_for
    from .batch import create_children

    plan = context_plan(connection, device, job)
    _validate_tally(result, plan)
    run = run_for(connection, device["tenant_id"], job["input"]["run_id"], True)
    target = target_from_references(
        result, device["id"], run["config"]["tally_target"]["discovery_id"]
    )
    expected_guid = run["config"]["tally_target"].get("expected_company_guid")
    if expected_guid and target["references"]["company_guid"] != expected_guid:
        raise ServiceError(
            "conflict",
            "The Tally company identity changed. Start a new bill run after checking the company.",
        )
    run["config"]["tally_target"] = target
    connection.execute(
        "UPDATE workflow_runs SET config=%s WHERE id=%s", (Jsonb(run["config"]), run["id"])
    )
    if run.get("parent_run_id"):
        connection.execute(
            "UPDATE workflow_runs SET config=config || %s WHERE tenant_id=%s AND id=%s",
            (Jsonb({"tally_target": target}), run["tenant_id"], run["parent_run_id"]),
        )
    if len(run["file_ids"]) > 1:
        create_children(connection, run)
    return {"references_prepared": True}


def recheck_target(connection, tenant, user, current):
    discovered = tally_target(connection, tenant, user, current["discovery_id"])
    if discovered.get("schema_only"):
        if any(discovered[key] != current[key] for key in ("company", "port", "device_id")):
            raise ServiceError(
                "conflict", "Tally source identity changed. Refresh source discovery."
            )
        return current
    return discovered


def validate_tally(data, target):
    from .catalog import validate_data

    validate_data(tally_mapping(target["discovery_id"])["sheets"][0], data)
    identity = business_identity(data)
    try:
        values = [Decimal(str(data[k])) for k in ("subtotal", "tax", "total")]
        if (
            any(
                not v.is_finite() or v < 0 or v.as_tuple().exponent < -2 or v * 100 > 2**53 - 1
                for v in values
            )
            or values[2] <= 0
        ):
            raise ValueError(
                "Amounts must be positive money values with at most two decimal places."
            )
        if values[0] + values[1] != values[2]:
            raise ValueError("Subtotal plus tax must equal total exactly.")
    except (InvalidOperation, TypeError, KeyError) as error:
        raise ValueError("Invalid bill amounts.") from error
    for key in ("vendor", "purchase_ledger") + (("tax_ledger",) if values[1] else ()):
        if data.get(key) not in target["ledgers"]:
            if key == "vendor":
                raise ValueError(
                    f"Supplier '{data.get(key)}' is missing from the confirmed Tally ledgers. "
                    "Add or map the supplier, refresh Source discovery, then continue this bill."
                )
            raise ValueError(f"{key} must match a discovered ledger exactly.")
    selected = [data["vendor"], data["purchase_ledger"]] + (
        [data["tax_ledger"]] if values[1] else []
    )
    if len(set(selected)) != len(selected):
        raise ValueError("Supplier, purchase and tax allocations require distinct ledgers.")
    if data.get("cost_code"):
        raise ValueError(
            "Cost allocations require a supported mapping; leave this bill for review."
        )
    return identity


def capture_tally_findings(result, target):
    """Hold invalid proposals before approval, preserving independent siblings.

    Discovery references are deterministic authority. An agent's confident
    interpretation must never make an unknown master silently writable.
    """
    unresolved = result.setdefault("unresolved", [])
    for record in result["records"]:
        try:
            validate_tally(record["data"], target)
        except ValueError as error:
            reason = str(error)
            if reason not in record["findings"]:
                record["findings"].append(reason)
            record["decision"] = "hold"
            if not any(i["source_file_id"] == record["source_file_id"] for i in unresolved):
                unresolved.append({"source_file_id": record["source_file_id"], "reason": reason})
    return result


def refreshed_tally_target(connection, tenant, user, current):
    """Explicit bill continuation may use refreshed masters in the same company.

    Never reroute a held bill to a different company or device. A pending or
    failed refresh must be confirmed before a new paid extraction can start.
    """
    latest = connection.execute(
        """SELECT id FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s
        AND device_id=%s AND config->'tally'->>'company'=%s
        ORDER BY created_at DESC LIMIT 1""",
        (tenant["id"], user["id"], current["device_id"], current["company"]),
    ).fetchone()
    target = tally_target(
        connection, tenant, user, latest["id"] if latest else current["discovery_id"]
    )
    if target.get("schema_only"):
        if any(target[k] != current[k] for k in ("company", "port", "device_id")):
            raise ServiceError(
                "conflict",
                "The Tally company identity changed. Start a new bill run after checking the company.",
            )
        return {**target, "expected_company_guid": current["references"]["company_guid"]}
    if target["destination_key"] != current["destination_key"]:
        raise ServiceError(
            "conflict",
            "The Tally company identity changed. Start a new bill run after checking the company.",
        )
    return target
