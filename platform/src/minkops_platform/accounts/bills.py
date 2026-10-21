"""Bill identity and destination reconciliation independent of model decisions.

Identity is business-derived, never a run UUID or upload filename. Destination
keys remain authoritative for backfills and externally created records.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from minkops_platform.errors import ServiceError


class HoldReason(ValueError):
    """A deterministic server-side hold with a stable code for attention labels."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def note_hold(record, error):
    """Record why a proposal is held, keeping a coded reason for its label."""
    record["findings"] = list(dict.fromkeys([*record["findings"], str(error)]))
    if getattr(error, "code", None):
        record["exception_codes"] = list(dict.fromkeys([*record.get("exception_codes", []), error.code]))


def add_note(record, text):
    """An internal observation about a bill; notes never hold it or ask for attention."""
    record["notes"] = list(dict.fromkeys([*record.get("notes", []), text]))


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
    from .vouchers import document_identity

    return document_identity(vendor, invoice, date.fromisoformat(str(data.get("date"))))


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


COMPANY_CONTEXT_REQUIRED = "Refresh Source Discovery to collect complete company context before a new bill run."


def tally_target(connection, tenant, user, discovery_id):
    """The run's destination: every company of one confirmed Source Discovery."""
    from minkops_platform import desktop, discovery

    catalog = discovery.require_ready(connection, tenant["id"], discovery_id, ["tally"])
    row = discovery.get_run(connection, tenant["id"], discovery_id)
    if row["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Use source discovery confirmed by your account.")
    desktop.owned_device(connection, tenant["id"], user["id"], row["device_id"])
    source = next(s["snapshot"] for s in catalog["sources"] if s["tool"] == "tally")
    if "companies" not in source:
        raise ServiceError("conflict", COMPANY_CONTEXT_REQUIRED)
    from .client_context import targets_from_snapshot

    return {
        "device_id": str(row["device_id"]),
        "discovery_id": str(discovery_id),
        "companies": targets_from_snapshot(source, row["device_id"], discovery_id),
        "company_mode": "infer",
        "locked_company_guid": None,
    }


def recheck_target(connection, tenant, user, current):
    if "companies" not in current:
        raise ServiceError("conflict", COMPANY_CONTEXT_REQUIRED)
    from minkops_platform import desktop

    desktop.owned_device(connection, tenant["id"], user["id"], current["device_id"])
    # The approved snapshot stays pinned. The native adapter rechecks exact
    # company/master versions and duplicates immediately before each write.
    return current


def allocation_entries(data, allocations=None):
    """Canonical tax lines; never infer rates or combine different tax ledgers."""
    if allocations is None:
        return [{"ledger": data.get("tax_ledger"), "amount": data["tax"]}] if data.get("tax") else []
    if not isinstance(allocations, list) or not 1 <= len(allocations) <= 8 or data.get("tax_ledger") is not None:
        raise ValueError("Select either one tax ledger or explicit split tax allocations.")
    result = []
    try:
        for line in allocations:
            if (not isinstance(line, dict) or not {"ledger", "amount"} <= set(line)
                    or set(line) - {"ledger", "amount", "ref", "evidence"}
                    or not isinstance(line["ledger"], str) or not line["ledger"].strip()
                    or type(line["amount"]) not in (int, float)):
                raise ValueError("Invalid tax allocation.")
            amount = Decimal(str(line["amount"]))
            if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2 or amount * 100 > 2**53 - 1:
                raise ValueError("Tax allocations require positive exact money values.")
            result.append({"ledger": line["ledger"], "amount": line["amount"]})
        if sum(Decimal(str(line["amount"])) for line in result) != Decimal(str(data["tax"])):
            raise ValueError("Tax allocations must equal the bill's total tax exactly.")
        if len({line["ledger"] for line in result}) != len(result):
            raise ValueError("Distinct tax allocations require distinct native ledgers.")
    except (InvalidOperation, KeyError, TypeError) as error:
        raise ValueError("Invalid tax allocation amounts.") from error
    return result


def capture_tally_findings(result, config):
    """Hold invalid proposals before approval, preserving independent siblings.

    Discovery references are deterministic authority. An agent's confident
    interpretation must never make an unknown master silently writable.
    """
    from .client_context import select_target
    from .vouchers import resolve, summary

    target = config["tally_target"]
    unresolved = result.setdefault("unresolved", [])
    for record in result["records"]:
        record["data"] = summary(record, config)
        try:
            selected = select_target(record, target)
            record["company_guid"] = selected["references"]["company_guid"]
            record["company_name"] = selected["company"]
            record["preview"] = resolve(record, config).preview()
        except ValueError as error:
            note_hold(record, error)
            record["decision"] = "hold"
            if not any(i["source_file_id"] == record["source_file_id"] for i in unresolved):
                unresolved.append({"source_file_id": record["source_file_id"], "reason": str(error),
                                   **({"code": error.code} if getattr(error, "code", None) else {})})
    return result


def refreshed_tally_target(connection, tenant, user, current):
    """Explicit bill continuation may use refreshed masters in the same company.

    Never reroute a held bill to a different company or device. A pending or
    failed refresh must be confirmed before a new paid extraction can start.
    """
    if "companies" not in current:
        raise ServiceError("conflict", COMPANY_CONTEXT_REQUIRED)
    latest = connection.execute(
        "SELECT id FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s AND device_id=%s AND config->>'depth'='client_context' ORDER BY created_at DESC LIMIT 1",
        (tenant["id"], user["id"], current["device_id"]),
    ).fetchone()
    updated = tally_target(
        connection, tenant, user, latest["id"] if latest else current["discovery_id"]
    )
    if {c["destination_key"] for c in current["companies"]} != {
        c["destination_key"] for c in updated["companies"]
    }:
        raise ServiceError("conflict", "Company scope changed. Start a new bill run.")
    return {**updated, "company_mode": current["company_mode"],
            "locked_company_guid": current["locked_company_guid"]}
