"""Accounts checks over inferred, confirmed business concepts."""

from minkops_connectors.excel import sheet_records

from .catalog import validate_data
from .repository import digest_bytes


def check_records(result, catalog, input_ids, contents, checks):
    """Validate destinations and report selected checks using confirmed concepts.

    Findings remain visible. Approval can acknowledge missing evidence but cannot
    authorize invalid schemas, duplicate appends or stale workbook writes.
    """
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        raise ValueError("Bill extraction must return records.")
    mappings = {
        (s["file_id"], s["sheet"], s.get("table")): s
        for s in catalog["sheets"]
        if s["role"] == "destination"
    }
    seen = set()
    for issue in result.get("unresolved", []):
        if (
            not isinstance(issue, dict)
            or issue.get("source_file_id") not in input_ids
            or not isinstance(issue.get("reason"), str)
            or not issue["reason"].strip()
        ):
            raise ValueError(
                "Unresolved routing must identify an authorized bill and explain the issue."
            )
        seen.add(issue["source_file_id"])
    for record in result["records"]:
        if record.get("source_file_id") not in input_ids:
            raise ValueError("Result refers to an unauthorized bill.")
        seen.add(record["source_file_id"])
        mapping = mappings.get(
            (record.get("destination_file_id"), record.get("sheet"), record.get("table"))
        )
        if not mapping:
            raise ValueError("Result must select a confirmed destination sheet.")
        if record.get("operation") not in ("append", "update"):
            raise ValueError("Result must select append or update.")
        if not isinstance(record.get("data"), dict):
            raise ValueError("Bill data must be an object.")
        record.setdefault("findings", [])
        if not isinstance(record["findings"], list) or not all(
            isinstance(v, str) for v in record["findings"]
        ):
            raise ValueError("Findings must be text.")
        evidence = record.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError("Records must include field evidence.")
        for e in evidence:
            if (
                not isinstance(e, dict)
                or e.get("field") not in [c["name"] for c in mapping["columns"]]
                or not isinstance(e.get("page"), int)
                or e["page"] < 1
                or not isinstance(e.get("quote"), str)
            ):
                raise ValueError("Field evidence must name a confirmed field and source page.")
        findings = list(record["findings"])
        try:
            validate_data(mapping, record["data"])
        except ValueError as error:
            findings.append(f"Validation: {error}")
        for c in mapping["columns"]:
            if c["concept"] == "entry_id" and c["name"] in record.get("derived_fields", {}):
                continue
            if record["data"].get(c["name"]) is not None and not any(
                e["field"] == c["name"] and e["quote"] for e in evidence
            ):
                findings.append(f"Missing source evidence: {c['name']}")
        concepts = {c["concept"]: c["name"] for c in mapping["columns"] if c["concept"]}
        data = record["data"]
        for column in mapping["columns"]:
            data.setdefault(column["name"], None)
        if "duplicate" in checks:
            keys = mapping["key_columns"]
            existing = sheet_records(contents[mapping["file_id"]], mapping)
            if any(
                all(
                    str(r["data"].get(k)).strip().casefold() == str(data.get(k)).strip().casefold()
                    for k in keys
                )
                for r in existing
            ):
                findings.append("Duplicate key exists in the destination; review an explicit edit.")
        for check, concept in [("vendor_match", "vendor"), ("cost_codes", "cost_code")]:
            if check not in checks:
                continue
            refs = []
            for ref in catalog["sheets"]:
                if ref["role"] != "reference":
                    continue
                column = next((c["name"] for c in ref["columns"] if c["concept"] == concept), None)
                if column:
                    refs.extend(
                        r["data"].get(column) for r in sheet_records(contents[ref["file_id"]], ref)
                    )
            v = data.get(concepts.get(concept, ""))
            if not refs or v is None:
                findings.append(f"{check}: insufficient confirmed reference evidence.")
            elif str(v).strip().casefold() not in {str(r).strip().casefold() for r in refs}:
                findings.append(f"{check}: no exact reference match.")
        if "totals" in checks:
            from decimal import Decimal, InvalidOperation

            try:
                subtotal = data.get(concepts.get("subtotal", ""))
                total = data.get(concepts.get("total", ""))
                tax_columns = [concepts[k] for k in ("cgst", "sgst", "igst") if k in concepts]
                if not tax_columns and "tax" in concepts:
                    tax_columns = [concepts["tax"]]
                if (
                    subtotal is None
                    or total is None
                    or not tax_columns
                    or any(data.get(k) is None for k in tax_columns)
                ):
                    findings.append("totals: insufficient mapped amounts to verify arithmetic.")
                elif abs(
                    Decimal(str(subtotal))
                    + sum(Decimal(str(data[k])) for k in tax_columns)
                    - Decimal(str(total))
                ) > Decimal("0.02"):
                    findings.append("totals: subtotal plus tax differs from total.")
            except (InvalidOperation, TypeError):
                findings.append("totals: invalid numeric evidence.")
        record["findings"] = list(dict.fromkeys(findings))
    if seen != set(input_ids):
        raise ValueError("Result must account for every selected input file.")
    result.setdefault("findings", [])
    if not isinstance(result["findings"], list) or not all(
        isinstance(v, str) for v in result["findings"]
    ):
        raise ValueError("Overall findings must be text.")
    return result


def populate_entry_ids(result, catalog, run_id):
    """Confirmed entry_id concepts are generated, never claimed as bill evidence."""
    mappings = {
        (s["file_id"], s["sheet"], s.get("table")): s
        for s in catalog["sheets"]
        if s["role"] == "destination"
    }
    for record in result.get("records", []):
        record["derived_fields"] = {}
        mapping = mappings.get(
            (record.get("destination_file_id"), record.get("sheet"), record.get("table"))
        )
        if not mapping:
            continue
        for c in mapping["columns"]:
            if c["concept"] == "entry_id":
                if c["type"] != "string":
                    raise ValueError("Generated entry IDs require a confirmed string column.")
                import json

                from .bills import business_identity, normalized

                concepts = {
                    col["concept"]: record["data"].get(col["name"])
                    for col in mapping["columns"]
                    if col["concept"]
                }
                if all(concepts.get(k) for k in ("vendor", "invoice_number", "date")):
                    identity = business_identity(concepts)
                else:
                    keys = [key for key in mapping["key_columns"] if key != c["name"]]
                    if not keys or any(record["data"].get(k) in (None, "") for k in keys):
                        raise ValueError("Generated IDs need complete confirmed business keys.")
                    identity = json.dumps([normalized(record["data"][key]) for key in keys])
                token = digest_bytes(
                    f"{mapping['sheet']}:{mapping.get('table')}:{identity}".encode()
                )[:16]
                record["data"][c["name"]] = f"MINKOPS-{token}"
                record["derived_fields"][c["name"]] = (
                    "Generated by Minkops from the confirmed bill identity."
                )
    return result
