"""One durable exception-sheet projection for web, Windows and CSV exports.

Reasons come from typed outcomes and structured identifiers. Model findings and
native diagnostic text are deliberately excluded from this public projection.
Attention remains file-scoped even when a PDF contains several bill records.
"""
import csv
import io

from minkops_platform.errors import ServiceError

from .checks import EXCEPTION_LABELS
from .tally_writes import HOLD_TITLES


REASONS = {
    "source_unreadable": "The bill could not be read reliably.",
    "not_a_bill": "This source does not contain a bill that can be entered.",
    "multiple_bills_unclear": "The separate bills in this file could not be identified reliably.",
    "required_value_missing": "A required bill value could not be confirmed from the source.",
    "source_values_conflict": "The source contains conflicting bill values.",
    "company_unresolved": "The destination company could not be identified reliably.",
    "supplier_unresolved": "The supplier could not be matched to exactly one Tally ledger.",
    "supplier_missing": "The supplier is missing from the company's confirmed Tally ledgers.",
    "classification_uncertain": "The appropriate accounting ledger could not be confirmed.",
    "unsupported_structure": "This bill requires accounting entries outside the supported save format.",
    "date_before_books": "The bill date is before the company's books beginning date.",
    "destination_changed": "The Tally destination changed after Source Discovery.",
    "voucher_type_unresolved": "A supported voucher type must be selected for this company.",
    "company_not_open": "The destination company must be open in Tally before this bill can be saved.",
    "no_company": "The destination company must be open in Tally before this bill can be saved.",
    "duplicate_company": "More than one open Tally company matches the destination identity.",
    "not_running": "Tally must be running and connected before this bill can be saved.",
    "port_closed": "Tally's local connection is unavailable.",
    "busy": "Tally is busy and could not complete the save.",
    "too_many": "Tally returned too many matching destinations to save safely.",
    "invalid_response": "Tally's response could not be verified.",
    "rejected": "Tally rejected this bill and its destination settings need attention.",
    "run_stopped": "The run was stopped before this bill was saved.",
    "save_waiting": "This bill is waiting for its destination before saving.",
    "save_interrupted": "The save was interrupted and its destination needs reconciliation.",
    "pc_unavailable": "The destination PC must reconnect before this bill can be saved.",
    "save_held": "This bill could not be saved and needs attention in the destination.",
    "human_review": "This bill was saved with a best guess and still requires human review.",
    "extraction_failed": "The bill could not be processed and needs an explicit recheck.",
    "manual_review": "This bill needs manual review in the original system.",
}
TITLE_CODES = {title: code for code, title in EXCEPTION_LABELS.items()}
TITLE_CODES.update({title: code for code, title in HOLD_TITLES.items()})
TITLE_CODES.update({
    "Run stopped": "run_stopped", "Save waiting": "save_waiting",
    "Save interrupted": "save_interrupted", "PC unavailable": "pc_unavailable",
    "Review in Tally": "save_held", "Review written bill": "human_review",
})


def reason_sentence(record, *, title=None):
    code = TITLE_CODES.get(title) if title else None
    if not code and record.get("save_hold"):
        code = record.get("save_hold_code", "save_held")
    if not code:
        codes = record.get("exception_codes") or [record.get("code")]
        code = codes[0]
    if code == "supplier_missing" or code == "supplier_unresolved":
        vendor = " ".join(str(record.get("data", {}).get("vendor") or "").split())[:160]
        if vendor:
            return (f"Supplier ‘{vendor}’ is missing from the company's confirmed Tally ledgers."
                    if code == "supplier_missing" else
                    f"Supplier ‘{vendor}’ could not be matched to exactly one Tally ledger.")
    return REASONS.get(code, REASONS["manual_review"])


def _status(record, *, deferred=False):
    if deferred or record.get("status") == "rejected":
        return "Not written (Do nothing)"
    return "Save held" if record.get("save_hold") else "Needs attention"


def export_unavailable(run):
    if run["state"] not in ("review", "completed", "failed", "stopped"):
        return "Export is ready after processing and destination saves have finished."
    result = run.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        return "Export is ready after the batch results have been combined."
    return None


def review(run, items=()):
    result = run.get("result") or {}
    records = result.get("records", [])
    names = {f["id"]: f["path"] for f in run["config"].get("file_provenance", [])}
    open_items = {i["event_key"]: str(i["id"]) for i in items if i["status"] == "pending"}

    def row(record, index=None, deferred=False):
        file_id = record["source_file_id"]
        prefix = f"bill:{run['id']}:{file_id}:"
        return {"source_file_id": file_id, "source_file": names.get(file_id, file_id),
                "record_index": index, "status": _status(record, deferred=deferred),
                "reason": reason_sentence(record),
                "attention_item_id": open_items.get(prefix + "bill", open_items.get(prefix + "supplier", ""))}

    rows = [row(record, index) for index, record in enumerate(records)
            if record.get("status") not in ("saved", "duplicate")]
    proposed = {r["source_file_id"] for r in records}
    # Defensive deduplication of file-only outcomes never combines bill records.
    seen = set(proposed)
    for key in ("unresolved", "deferred"):
        for item in result.get(key, []):
            if item["source_file_id"] not in seen:
                rows.append(row(item, deferred=key == "deferred"))
                seen.add(item["source_file_id"])
    return {"rows": rows, "saved": sum(r.get("status") == "saved" for r in records),
            "duplicates": sum(r.get("status") == "duplicate" for r in records),
            "export_unavailable": export_unavailable(run)}


def _text(value):
    """Escape text cells only; negative numeric amounts retain their number type."""
    text = str(value) if value is not None else ""
    return "'" + text if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")) else text


def exception_csv(headers, rows):
    """Shared exception export: BOM, quoted CSV and text-only formula escaping."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([value if type(value) in (int, float) else _text(value) for value in row])
    return output.getvalue().encode("utf-8-sig")


def export_csv(run, items=()):
    unavailable = export_unavailable(run)
    if unavailable:
        raise ServiceError("conflict", unavailable)
    view = review(run, items)
    headers = ["Source file", "Invoice number", "Supplier", "Bill date", "Amount before taxes",
               "Tax", "Tax allocations", "Total", "Company", "Status", "Reason", "Attention item ID"]
    rows = []
    for row in view["rows"]:
        record = run["result"]["records"][row["record_index"]] if row["record_index"] is not None else {}
        data = record.get("data", {})
        # Tally's supported schema has typed amounts. Malformed/legacy text is
        # escaped instead of being mistaken for a trusted numeric cell.
        taxes = "; ".join(f"{t.get('ledger') or 'Tax'}: {t['amount']}" for t in record.get("tax_allocations", []))
        rows.append([row["source_file"], data.get("invoice_number"), data.get("vendor"), data.get("date"),
                     data.get("subtotal"), data.get("tax"), taxes, data.get("total"),
                     record.get("company_name") or run["config"].get("tally_target", {}).get("company"),
                     row["status"], row["reason"], row["attention_item_id"]])
    return exception_csv(headers, rows)


def attention_items(connection, run):
    return connection.execute("""SELECT id,event_key,status FROM attention_items
        WHERE tenant_id=%s AND task_id=%s AND status='pending'""", (run["tenant_id"], run["task_id"])).fetchall()
