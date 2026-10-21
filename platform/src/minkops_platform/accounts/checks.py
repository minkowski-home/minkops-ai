"""Coverage, evidence and typed exceptions for bill voucher proposals."""

from .holds import BILL, EXCEPTION, view

# Short attention labels for coded holds: the agent's closed set of genuine
# blockers plus deterministic server-side reasons (see holds.py).
EXCEPTION_LABELS = view("label", scope=BILL, kinds=(EXCEPTION,))


def adopt_exceptions(result):
    """Translate the typed agent contract into internal blocking findings.

    Only coded exceptions block a bill; notes stay internal observations, so a
    successful check or a possible duplicate can no longer hold a routine bill.
    Results pinned to the older free-text contract pass through unchanged.
    """
    if "exceptions" not in result:
        return result

    def adopt(holder):
        exceptions = holder.pop("exceptions", [])
        holder["findings"] = [exception["detail"] for exception in exceptions]
        holder["exception_codes"] = list(dict.fromkeys(e["code"] for e in exceptions))

    for record in result["records"]:
        adopt(record)
    adopt(result)
    return result


def check_voucher_records(result, input_ids):
    """Coverage and evidence for voucher proposals; accounting rules live in vouchers.check."""
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        raise ValueError("Bill extraction must return records.")
    seen = {i["source_file_id"] for i in result.get("deferred", []) if i.get("source_file_id") in input_ids}
    for issue in result.get("unresolved", []):
        if (not isinstance(issue, dict) or issue.get("source_file_id") not in input_ids
                or not isinstance(issue.get("reason"), str) or not issue["reason"].strip()):
            raise ValueError("Unresolved routing must identify an authorized bill and explain the issue.")
        seen.add(issue["source_file_id"])
    for record in result["records"]:
        if record.get("source_file_id") not in input_ids:
            raise ValueError("Result refers to an unauthorized bill.")
        seen.add(record["source_file_id"])
        if record.get("operation") not in ("append", "update"):
            raise ValueError("Result must select append or update.")
        record.setdefault("findings", [])
        if not isinstance(record["findings"], list) or not all(isinstance(v, str) for v in record["findings"]):
            raise ValueError("Findings must be text.")
        if not isinstance(record.get("evidence"), list) or any(
                not isinstance(e, dict) or not isinstance(e.get("page"), int) or e["page"] < 1
                or not isinstance(e.get("quote"), str) for e in record["evidence"]):
            raise ValueError("Field evidence must name a source page.")
        quoted = {e.get("field") for e in record["evidence"] if e["quote"].strip()}
        missing = [field for field in ("number", "date", "total", "supplier") if field not in quoted]
        if missing:
            record["findings"] = list(dict.fromkeys([*record["findings"], f"Missing source evidence: {', '.join(missing)}"]))
    if seen != set(input_ids):
        raise ValueError("Result must account for every selected input file.")
    result.setdefault("findings", [])
    if not isinstance(result["findings"], list) or not all(isinstance(v, str) for v in result["findings"]):
        raise ValueError("Overall findings must be text.")
    return result
