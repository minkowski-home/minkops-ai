"""Bill entry on runs: each bill file read in its own tool session, its proposal checked once answered.

At launch each selected file becomes an item that waits until the client's
PCs have refreshed their Tally copies. Its session reads the file's pages, as
images and, where the PDF has one, a text layer (minkops_connectors.documents),
looks up the client's books, and answers with the bills the file holds,
numbered in the order they appear: a final answer the provider constrains to
the proposal's schema (PROPOSAL). Each bill is bound to the company it is
addressed to and checked against that company's pinned mirror by the voucher
gate (vouchers.check); what the gate rejects goes back to the same session to
correct. A file holds one record per bill.

When the last item settles, a bill repeated across files is written once, and
files printing different versions of one bill all hold. Approved bills become
native writes (writes.py). A new supplier is created only on a person's
explicit decision and verified by native readback; then its bills are checked
again with it, and the approved one is written.

The printed bill decides the facts: a total or round-off the text layer does
not print is refused, and a reading that changes after a refusal goes to review.
"""

import base64
import contextlib
import json
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path

from jsonschema import ValidationError

from minkops_connectors import einvoice
from minkops_connectors.documents import pages
from minkops_platform import work
from minkops_platform.errors import ServiceError
from minkops_platform.files import files_for
from minkops_platform.lanes import Session
from minkops_platform.run_controls import control_state, require_active, resolve_request
from minkops_platform.runtime.tools import Answer, Tool, ToolError
from minkops_platform.workflows import resolve_run_config

from . import desk_tools, memory, mirror, practice, supplier_gst, sync, writes
from .desk_tools import COMPANY, Desk, reference, schema
from .holds import ACTIONS, BILL, EXCEPTION, hold
from .holds import actions as hold_actions
from .voucher_types import base_types
from .vouchers import HoldReason, check, correction_reason, narration_token, observed_bill, rupees

KIND = "bill"
# A proposal and at most two resubmissions, per bill.
ATTEMPTS = 3
MAX_FILES, MAX_BILLS = 50, 20
MAX_BYTES = 40_000_000
SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
EXCEPTIONS = ("source_unreadable", "not_a_bill", "multiple_bills_unclear", "required_value_missing",
              "source_values_conflict", "company_unresolved", "supplier_unresolved", "supplier_missing",
              "classification_uncertain", "unsupported_structure")
# Gate holds no resubmission can clear: the printed date or origin, or a supplier only a person may create.
FINAL = {"date_before_books", "date_outside_company_period", "identity_rule_unknown", "supplier_missing"}
# Native holds the companion names; any other unverified save holds as save_held, with its message.
SAVE_HOLDS = {"company_not_open", "no_company", "duplicate_company", "not_running", "port_closed", "busy", "too_many",
              "invalid_response", "rejected", "save_interrupted", "destination_changed"}
# A bill offers these of its holds' actions; a best guess and a new supplier also need record-specific checks.
OFFERED = ("nothing", "retry", "guess", "supplier", "retry_save")
GUESSED = "Written as a best guess; review it in Tally."
UNPRECEDENTED = ("This supplier's bills have not been booked this way before. Review the voucher type and ledgers "
                 "before approving.")
DEMOTED = ("Someone changed a bill booked this way in Tally after Minkops saved it. Review the voucher type and "
           "ledgers before approving.")
GUESSED_BOOKING = ("This supplier's bills were last booked this way as a best guess. Review the voucher type and "
                   "ledgers before approving.")
BOOKING_REVIEWS = (UNPRECEDENTED, DEMOTED, GUESSED_BOOKING)
# The voucher families a supplier's bill is booked in, as Tally's base voucher types name them.
PURCHASE_SIDE = {"purchase", "journal", "debit note"}


# --- launch ---------------------------------------------------------------------------

def launch(connection, *, tenant, user, client, workflow, definition, body):
    """Queue the client's PCs to refresh, and create the run with one item and one waiting bill per file."""
    file_ids = [str(file_id) for file_id in body["file_ids"]]
    if not file_ids or len(file_ids) != len(set(file_ids)) or len(file_ids) > MAX_FILES:
        raise ServiceError("invalid", f"Select between 1 and {MAX_FILES} bill files, each once.")
    try:
        config = resolve_run_config(definition, workflow["config_values"], body.get("config") or {})
    except (ValidationError, ValueError) as error:
        raise ServiceError("invalid", "These bill settings are not valid.") from error
    request = {"workflow": workflow["key"], "file_ids": file_ids, "config": body.get("config") or {}}
    fingerprint, previous = resolve_request(connection, tenant["id"], body["request_key"], request,
                                            work.find_by_request)
    if previous:
        return previous
    files = files_for(connection, tenant["id"], file_ids)
    if any(not f["current"] for f in files):
        raise ServiceError("conflict", "Refresh the changed files first.")
    if any(Path(f["path"]).suffix.lower() not in SUFFIXES for f in files):
        raise ServiceError("invalid", "Bills must be PDF, PNG, JPEG or WebP files.")
    if sum(len(f["content"]) for f in files) > MAX_BYTES:
        raise ServiceError("invalid", "Select at most 40 MB of bills.")
    companies, devices = desk_tools.prepare(connection, tenant, user, client)
    if config["company_mode"] == "locked" and config.get("locked_company_guid") not in {c["guid"] for c in companies}:
        raise ServiceError("invalid", "Choose one of this client's companies to enter every bill into.")
    paths = {str(f["id"]): f["path"][:200] for f in files}
    config["files"] = [{"id": file_id, "path": paths[file_id]} for file_id in file_ids]
    run = work.launch(connection, tenant_id=tenant["id"], client_id=client["id"], workflow=workflow,
                      handler="desk.bill", definition_version=definition.metadata["version"],
                      bundle=definition.session_bundle, actor_id=user["id"], request_key=body["request_key"],
                      request_hash=fingerprint, config=config,
                      title=work.title("Bill entry", [Path(paths[file_id]).name for file_id in file_ids]),
                      items=[work.ItemSpec(KIND, {"file_id": file_id}, waiting_on=sync.blocker(devices[0]["id"]))
                             for file_id in file_ids], describe=describe)
    items = connection.execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()
    for item in items:
        work.add_records(connection, item, [_blank(item, paths[item["source"]["file_id"]], 1)])
    desk_tools.note_unavailable(connection, run)
    return run


def _blank(item, path, number):
    return {"kind": KIND, "source": {"file_id": item["source"]["file_id"], "bill": number},
            "facts": {"file": path, "bill": number}}


# --- sessions -------------------------------------------------------------------------

class Bills(Desk):
    """A bill session's state: the desk, the file's item, the amounts its text layer prints (_figures), and the
    e-invoices its signed QR codes register (minkops_connectors.einvoice)."""

    def __init__(self, connection, run, item, printed, einvoices=()):
        super().__init__(connection, run)
        self.item, self.printed, self.einvoices = item, printed, list(einvoices)


FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")
ROUNDING = re.compile(r"round|r/o", re.IGNORECASE)


def _paise(value):
    """Exact paise of an amount, a JSON number or printed text; None beyond two decimals."""
    try:
        amount = Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None
    return int(amount * 100) if amount.is_finite() and amount.as_tuple().exponent >= -2 else None


def _figures(read):
    """The amounts the file's text layers print, in paise, and those printed on round-off lines.

    None when a page is a scan: its figures are only in its image.
    """
    if not all(page["text"] for page in read):
        return None
    every, rounding = set(), set()
    for page in read:
        for text in page["text"].splitlines():
            found = {cents for token in FIGURE.findall(text) if (cents := _paise(token)) is not None}
            every |= found
            if ROUNDING.search(text):
                rounding |= found
    return {"total": frozenset(every), "round_off": frozenset(rounding)}


def _records(connection, item, *, lock=False):
    return connection.execute(
        f"SELECT * FROM run_records WHERE item_id=%s AND kind=%s ORDER BY position{' FOR UPDATE' if lock else ''}",
        (item["id"], KIND)).fetchall()


def _open(record):
    """A later reading may replace this bill's proposal: nothing decided, written or held by the writer."""
    return record["status"] in ("pending", "proposed") or (
        record["status"] == "held" and all(hold(code).kind == EXCEPTION for code in record["hold_codes"]))


def _content(connection, run, desk, file, read, decided):
    config = run["config"]
    refs = desk.issue(connection, "company", None, list(desk.parts))
    header = {"file": Path(file["path"]).name, "pages": len(read), "company_mode": config["company_mode"],
              "companies": [{"name": part["name"], "ref": refs[part["guid"]], "books_from": part["books_from"].isoformat()}
                            for parts in desk.parts.values() for part in parts]}
    if config["company_mode"] == "locked":
        header["locked_company"] = refs[config["locked_company_guid"]]
    if decided:
        header["decided_bills"] = decided
    content = [{"type": "input_text", "text": json.dumps(header, ensure_ascii=False)}]
    for found in desk.einvoices:
        content.append({"type": "input_text", "text": _registered_text(found)})
    for page in read:
        layer = f"Text layer:\n{page['text']}" if page["text"] else "A scan with no text layer."
        content.append({"type": "input_text", "text": f"Page {page['page']} of {len(read)}. {layer}"})
        content.append({"type": "input_image",
                        "image_url": "data:image/jpeg;base64," + base64.b64encode(page["image"]).decode()})
    return content


def session(connection, run, item):
    run = desk_tools.ready(connection, run)
    records = _records(connection, item)
    if not any(r["status"] == "pending" for r in records):
        return None
    file = files_for(connection, run["tenant_id"], [item["source"]["file_id"]])[0]
    try:
        read = pages(bytes(file["content"]), Path(file["path"]).suffix)
    except ValueError as error:
        _hold_pending(connection, item, "source_unreadable", str(error))
        return None
    einvoices = [{"page": page["page"], **found} for page in read for code in page["codes"]
                 if (found := einvoice.read(code))]
    desk = Bills(connection, run, item, _figures(read), einvoices)
    pinned = desk_tools.bundle(connection, run)
    # A recheck reads the whole file again; the bills already decided keep their numbers.
    decided = [{"bill": r["position"] + 1, "status": r["status"],
                **{key: r["facts"][key] for key in ("supplier", "number", "date") if key in r["facts"]}}
               for r in records if not _open(r)]
    return Session(model=pinned["model"], instructions=pinned["instructions"], reasoning=desk_tools.reasoning(pinned),
                   service_tier=pinned.get("service_tier"),
                   content=_content(connection, run, desk, file, read, decided), tools={**desk_tools.TOOLS, **BILL_TOOLS},
                   state=desk, answer=PROPOSAL)


def _hold_pending(connection, item, code, reason, *, refusals=True):
    """Hold the bills no proposal reached; a bill refused at its last reading holds for that refusal."""
    connection.execute(
        """UPDATE run_records SET status='held',
               hold_codes=ARRAY[coalesce(CASE WHEN %(refusals)s THEN checks->>'code' END, %(code)s)],
               review_reasons=ARRAY[left(coalesce(CASE WHEN %(refusals)s THEN checks->>'error' END, %(reason)s), 300)],
               version=version+1, updated_at=now()
           WHERE item_id=%(item)s AND status='pending'""",
        {"refusals": refusals, "code": code, "reason": reason, "item": item["id"]})


# --- propose --------------------------------------------------------------------------

def _iso(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return None


READ = ("number", "date", "total", "supplier_name", "supplier_gstin", "taxable", "tax")
MONTHS = {name: number for number, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
NUMERIC_DATE = re.compile(r"(?<![\d/.-])(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?![\d/.-])")
NAMED_DATE = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[-/. ]*([A-Za-z]{3})[a-z]*\.?[-/., ]*(\d{4}|\d{2})(?!\d)")
MONTH_FIRST = re.compile(r"\b([A-Za-z]{3})[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})(?!\d)")
ISO_DATE = re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")
# No bill this desk reads is dated before this, or more than a year after its run.
EARLIEST_BILL = date(2000, 1, 1)


def printed_dates(text):
    """Every date a printed text can mean, as YYYY-MM-DD: a numeric one both day first and month first."""
    found = set()

    def add(year, month, day):
        year = int(year) + (2000 if len(year) == 2 else 0)
        with contextlib.suppress(ValueError):  # a day past its month's end is no date
            found.add(date(year, int(month), int(day)).isoformat())
    for day, month, year in NUMERIC_DATE.findall(text):
        add(year, month, day)
        add(year, day, month)
    for day, name, year in NAMED_DATE.findall(text):
        if name.lower() in MONTHS:
            add(year, MONTHS[name.lower()], day)
    for name, day, year in MONTH_FIRST.findall(text):
        if name.lower() in MONTHS:
            add(year, MONTHS[name.lower()], day)
    for year, month, day in ISO_DATE.findall(text):
        add(year, month, day)
    return found


def _dated(run, bill):
    """The date a session wrote must be one the bill prints, and one a bill could carry.

    Bills print dates day first (01-Oct-2026). Written into a year-first field, one can come out as 0110-01-01: a
    real date, but not the bill's. Refused rather than held, the bill is read again; only a date that agrees with
    what the session quoted reaches the checks a person must resolve, such as one before the books begin.
    """
    value = (bill.get("document") or {}).get("date")
    if value is None:
        return
    issued = _iso(value)
    if issued is None:
        raise HoldReason("source_values_conflict", f"{value} is not a date. Write the date year first, as YYYY-MM-DD: a "
                                                   "bill printing 01-Oct-2026 is dated 2026-10-01.")
    quotes = [e["quote"] for e in bill.get("evidence") or [] if e.get("field") == "date" and printed_dates(e["quote"])]
    printed = set().union(*map(printed_dates, quotes))
    if printed and issued not in printed:
        raise HoldReason("source_values_conflict", (
            f"The bill prints its date as \u201c{quotes[0]}\u201d, which is {' or '.join(sorted(printed))}, not {value}. "
            "Write the date year first, as YYYY-MM-DD."))
    if not EARLIEST_BILL <= date.fromisoformat(issued) <= run["created_at"].date() + timedelta(days=366):
        raise HoldReason("source_values_conflict", f"{value} is not a plausible bill date. Read the date the bill prints "
                                                   "again, and write it year first, as YYYY-MM-DD.")


def _changed(first, now):
    """What a resubmission reads differently from the bill's first reading."""
    return [f"{key} {first[key]} became {now.get(key)}" for key in READ
            if first.get(key) is not None and now.get(key) != first[key]]


def _printed(desk, bill):
    """The total and any round-off must be amounts the text layer prints: they are what a voucher balances on."""
    if desk.printed is None:
        return
    figures = [("total", "total", bill["document"].get("total"))] + [
        ("round_off", "round-off", line["amount"]) for line in bill["voucher"]["lines"] if line["role"] == "round_off"]
    for kind, what, value in figures:
        if isinstance(value, (int, float)) and _paise(value) not in desk.printed[kind]:
            raise HoldReason("source_values_conflict", f"The bill's text does not print {rupees(_paise(value))} as its {what}. "
                                                       "Use the figure the bill prints.")


SIGNED = {"verified": "a signed e-invoice QR code, verified as signed by {signer}",
          "unverified": "a signed e-invoice QR code whose signer Minkops cannot verify",
          "altered": "an e-invoice QR code that fails {signer}'s signature, so what it says may have been altered"}


def _registered_text(found):
    """How the session is told what a signed e-invoice code on a page registers."""
    values = {"kind": found["kind"], "number": found["number"], "date": found["date"],
              "total": f"{found['total_cents'] / 100:.2f}", "seller_gstin": found["seller_gstin"],
              "buyer_gstin": found["buyer_gstin"], "irn": found["irn"]}
    return (f"Page {found['page']} carries {SIGNED[found['status']].format(signer=found['signer'])}. It registers "
            f"{json.dumps(values, ensure_ascii=False)}. Read the bill against these values.")


def _registered(connection, desk, bill, company, count):
    """The e-invoice a bill's signed QR code registers, which its reading must agree with; None without one.

    A code belongs to the bill with its number, or to a file's only bill when it
    is the file's only code. What it registers binds the reading's number,
    date, total, seller and kind, and its buyer must be the routed company.
    """
    document = bill["document"]
    same = [found for found in desk.einvoices if _key(found["number"]) == _key(document["number"])]
    found = (same or (desk.einvoices if len(desk.einvoices) == 1 and count == 1 else [None]))[0]
    if found is None:
        return None
    where = f"The e-invoice QR code on page {found['page']}"
    if found["status"] == "altered":
        raise HoldReason("source_values_conflict", f"{where} fails {found['signer']}'s signature, so what it says may "
                                                   "have been altered. Check this bill with the supplier.", final=True)
    kind = "credit_note" if found["kind"] == "credit_note" else "invoice"
    conflicts = [f"its {what} is {theirs}" for what, theirs, ours in (
        ("number", found["number"], _key(document["number"]) == _key(found["number"])),
        ("date", found["date"], document["date"] == found["date"]),
        ("total", f"{found['total_cents'] / 100:.2f}", _paise(document["total"]) == found["total_cents"]),
        ("seller GSTIN", found["seller_gstin"], (document.get("supplier_gstin") or "").upper() == found["seller_gstin"]),
        ("document kind", kind.replace("_", " "), document["kind"] == kind)) if not ours]
    if conflicts:
        raise HoldReason("source_values_conflict", f"{where} says {'; '.join(conflicts)}. Read the bill against it.")
    buyer = found["buyer_gstin"]
    if buyer and buyer != "URP" and buyer not in desk.gstins(connection, company):
        raise HoldReason("company_unresolved", f"{where} registers the bill to buyer GSTIN {buyer}, which is not "
                                               f"{company['name']}'s.")
    return found


def _key(number):
    return re.sub(r"\s", "", str(number or "")).casefold()


def _resize(connection, item, records, count):
    """Grow or shrink the file's bills to `count`; a bill no longer found holds if a person acted on it."""
    if count > len(records):
        work.add_records(connection, item, [_blank(item, records[0]["facts"]["file"], n + 1)
                                            for n in range(len(records), count)])
    surplus = records[count:]
    if not surplus:
        return
    acted = {row["record_id"] for row in connection.execute(
        "SELECT DISTINCT record_id FROM record_decisions WHERE record_id = ANY(%s)", ([r["id"] for r in surplus],))}
    connection.execute("DELETE FROM run_records WHERE id = ANY(%s)",
                       ([r["id"] for r in surplus if r["id"] not in acted],))
    for record in surplus:
        if record["id"] in acted:
            work.update_record(connection, record, status="held", hold_codes=["multiple_bills_unclear"],
                               review_reasons=["A later reading of this file did not find this bill."])


def propose(call, arguments):
    desk, connection = call.state, call.connection
    count, bills = arguments["count"], arguments["bills"]
    numbers = [bill["bill"] for bill in bills]
    if len(set(numbers)) != len(numbers) or max(numbers) > count:
        raise ToolError(f"Number this file's bills from 1 to {count}, each once.")
    records = _records(connection, desk.item, lock=True)
    decided = [r for r in records if not _open(r)]
    if decided and decided[-1]["position"] >= count:
        last = decided[-1]
        raise ToolError(f"Bill {last['position'] + 1} of this file is already {last['status']}, so the file holds at "
                        f"least {last['position'] + 1} bills.")
    _resize(connection, desk.item, records, count)
    by_number = {r["position"] + 1: r for r in _records(connection, desk.item, lock=True)}
    results = []
    for bill in bills:
        record = by_number[bill["bill"]]
        if not _open(record):
            results.append({"bill": bill["bill"], "status": record["status"], "reason": "Already decided."})
            continue
        results.append({"bill": bill["bill"], **_propose_one(connection, desk, record, bill, count)})
    waiting = [number for number, r in by_number.items() if r["status"] == "pending"]
    return {"bills": results, **({"still_pending": waiting} if waiting else {})}


def _cited(connection, desk, bill):
    """The bill as the checks and its plan read it: the company and masters it cites by reference, by GUID.

    A reference the session was not given, or one naming another kind of master or another company's, is
    refused with how to find the right one; the session may propose the bill again.
    """
    out = {key: value for key, value in bill.items() if key != "company"}
    try:
        out["company_guid"] = desk.resolve(connection, "company", [bill["company"]])[bill["company"]] \
            if bill.get("company") else None
    except ToolError as refusal:
        raise HoldReason("company_unresolved", str(refusal)) from None
    voucher, company = bill.get("voucher"), desk.companies.get(out["company_guid"])
    if voucher is None:
        return out
    try:
        guid = lambda kind, ref: desk.resolve(connection, kind, [ref], company)[ref] if ref else None  # noqa: E731
        lines = []
        for line in voucher["lines"]:
            centre = guid("cost_centre", line["cost_centre"])
            lines.append({**{key: value for key, value in line.items() if key not in ("ledger", "cost_centre")},
                          "ledger_guid": guid("ledger", line["ledger"]), "cost_centre_guid": centre,
                          "cost_category_guid": desk.category(connection, company, centre) if centre else None})
        out["voucher"] = {
            **{key: value for key, value in voucher.items() if key not in ("voucher_type", "party", "lines", "items")},
            "voucher_type_guid": guid("voucher_type", voucher["voucher_type"]),
            "party": {"ledger_guid": guid("ledger", voucher["party"]["ledger"]),
                      "new_supplier": voucher["party"]["new_supplier"], "evidence": voucher["party"]["evidence"]},
            "lines": lines,
            **({"items": [{**{key: value for key, value in item.items() if key not in ("item", "ledger", "godowns")},
                           "item_guid": guid("stock_item", item["item"]), "ledger_guid": guid("ledger", item["ledger"]),
                           "godowns": [{"godown_guid": guid("godown", place["godown"]), "quantity": place["quantity"],
                                        "amount": place["amount"]} for place in item["godowns"]]}
                          for item in voucher["items"]]} if voucher.get("items") else {})}
    except ToolError as refusal:
        raise HoldReason("classification_uncertain", str(refusal)) from None
    return out


def _company(desk, bill):
    guid = bill.get("company_guid")
    if guid not in desk.parts:
        return None
    return desk.company(guid, on=_iso((bill.get("document") or {}).get("date")))


def _addressed(connection, desk, document, company):
    """Hold a bill whose buyer GSTIN is another of the client's companies': the GSTIN routes it, whatever its name
    resembles. Checked here, where every company is in view: a company Tally keeps without GST has no registration
    of its own to compare (vouchers.check)."""
    buyer = (document.get("buyer_gstin") or "").strip().upper()
    if not buyer or buyer in desk.gstins(connection, company):
        return
    other = desk.addressee(connection, buyer, company)
    if other is None:
        return
    if other.get("unavailable"):
        raise HoldReason("company_unresolved", f"The bill is addressed to GSTIN {buyer}, which is {other['name']}'s, "
                                               f"whose books were on {other['device_name']}, which was disconnected. "
                                               "Continue them on the PC that holds them now, then enter this bill in a "
                                               "new run.", final=True)
    raise HoldReason("company_unresolved", f"The bill is addressed to GSTIN {buyer}, which is {other['name']}'s, not "
                                           f"{company['name']}'s. Choose {other['name']} with find_company.")


def _facts(record, document, company):
    read = {"supplier": document.get("supplier_name"), "number": document.get("number"),
            "date": document.get("date"), "total": document.get("total"),
            "company": company["name"] if company else None}
    return {"file": record["facts"]["file"], "bill": record["position"] + 1,
            **{key: value for key, value in read.items() if value is not None}}


def _propose_one(connection, desk, record, bill, count):
    run, document = desk.run, bill["document"] or {}
    earlier = record["checks"] or {}
    if earlier.get("final"):
        # Only a person's recheck reads a bill held by a final check again.
        return {"status": "held", "code": record["hold_codes"][0], "reason": record["review_reasons"][0]}
    submissions = earlier.get("submissions", 0) + 1
    if submissions > ATTEMPTS:
        return {"status": "refused", "reason": "No more resubmissions for this bill; it waits for review."}
    reading = {key: document.get(key) for key in READ}
    checks = {"submissions": submissions, "read": earlier.get("read") or reading}
    review = [f"The bill was read differently after a refusal: {'; '.join(changed)}."
              for changed in [_changed(checks["read"], reading)] if changed]
    company = facts = None
    locked = run["config"].get("locked_company_guid") if run["config"]["company_mode"] == "locked" else None
    try:
        _dated(run, bill)
        bill = _cited(connection, desk, bill)
        company = _company(desk, bill)
        facts = _facts(record, document, company)
        cited = desk.cite(connection, bill["rules"])
        if bill["exception"]:
            return _hold(connection, desk, record, bill, company, bill["exception"]["code"],
                         bill["exception"]["detail"], facts=facts, checks=checks, rules=cited,
                         review=[*review, *_besides(connection, desk, bill, company)])
        if company is None:
            raise HoldReason("company_unresolved", "Choose the buyer among the client's companies with find_company, "
                                                   "or propose the exception company_unresolved.")
        if locked and company["guid"] != locked:
            raise HoldReason("company_unresolved", "This run enters every bill into its locked company. When the bill "
                                                   "is addressed to another buyer, propose company_unresolved.")
        _addressed(connection, desk, document, company)
        registered = None
        if bill["document"] and bill["voucher"]:
            _printed(desk, bill)
            registered = _registered(connection, desk, bill, company, count)
        bound = check(bill, desk.view(connection, company), company, until=desk.until(company))
    except HoldReason as refusal:
        facts = facts or _facts(record, document, company)
        if refusal.code in FINAL or refusal.final or submissions >= ATTEMPTS:
            return _hold(connection, desk, record, bill, company, refusal.code, str(refusal), facts=facts,
                         checks={**checks, "final": refusal.code in FINAL or refusal.final}, review=review)
        work.update_record(connection, record, status="pending", hold_codes=[], review_reasons=[], facts=facts,
                           company_id=company["id"] if company else None, proposal={"bill": bill},
                           checks={**checks, "code": refusal.code, "error": desk.spelled(connection, str(refusal))[:300]})
        return {"status": "rejected", "reason": str(refusal)}
    if registered:
        # The reviewer sees which IRP registered the bill, and whether its signature verified.
        facts = {**facts, "einvoice": {key: registered[key] for key in ("status", "signer", "irn", "page")}}
    note, precedents = _precedent(connection, desk, company, bound)
    review += [*bound.notes, *([note] if note else [])]
    checks = {**checks, "precedents": precedents}
    waits = _waits(connection, company, bill, bound)
    if waits:
        # An open practice is a one-click question whose answer releases the bill; a tracked one is final.
        code, reason, probe = waits
        return _hold(connection, desk, record, bill, company, code, reason, facts=facts, review=review, rules=cited,
                     checks={**checks, "practice": probe, **({"final": True} if code != "practice_question" else {})})
    work.update_record(connection, record, status="proposed", hold_codes=[], review_reasons=review, facts=facts,
                       company_id=company["id"], checks=checks, proposal=_proposal(bill, bound, rules=cited))
    # Review notes are for the person approving: told of one, a session would rebook a sound bill to avoid it.
    return {"status": "accepted"}


# Practices that track an item-wise purchase's goods in Tally, where such a bill is entered.
TRACKED = {
    "receipt_notes": "Receipt Notes are in use in {company}, so an item-wise purchase follows its receipt note there. "
                     "Enter this bill in Tally.",
    "purchase_orders": "Purchase orders are in use in {company}, so an item-wise purchase is matched to its order "
                       "there. Enter this bill in Tally.",
}


def _waits(connection, company, bill, bound):
    """Why the company's practice holds this bill, as (code, reason, probe), or None.

    A receipt-register stamp needs to know where the company records it, and an
    item-wise purchase whether receipt notes or purchase orders track its goods.
    A taxed bill needs to know which GST ledgers the company uses, and one with a
    discount line how it books discounts, while the books leave that to its client.
    """
    probes = ["receipt_register"] if (bill.get("document") or {}).get("receipt_register") else []
    roles = {line["role"] for line in (bill.get("voucher") or {}).get("lines") or []}
    enforced = [probe for probe, role in (("gst_ledgers", "tax"), ("discounts", "discount"))
                if role in roles and practice.is_open(connection, company, probe)]
    for probe in [*probes, *enforced, *(TRACKED if bound.stock else ())]:
        settled = practice.settled(connection, company, probe)
        if settled is None:
            return "practice_question", hold("practice_question").reason, probe
        if probe in TRACKED and settled.get("in_use"):
            return "unsupported_structure", TRACKED[probe].format(company=company["name"]), probe
    return None


def _proposal(bill, bound, **extra):
    return {"bill": bill, "preview": bound.preview(), "identity": bound.identity,
            "destination_key": bound.destination_key, **extra}


def _besides(connection, desk, bill, company):
    """What the checks find in a voucher proposed with an exception, for the person who resolves the exception.

    Held for its own question, the bill never reaches the checks; told only that, a person answers it and meets the
    next problem on the recheck. Only a question about how to book the bill is checked this way: when the reading or
    the supplier is in doubt, so is every check built on it.
    """
    if (company is None or bill["exception"]["code"] not in ("classification_uncertain", "unsupported_structure")
            or not bill.get("document") or not (bill.get("voucher") or {}).get("lines")):
        return []
    try:
        check(bill, desk.view(connection, company), company, until=desk.until(company))
    except HoldReason as fault:
        return [f"Checking the proposed voucher: {desk.spelled(connection, str(fault))}"[:300]]
    return []


def _hold(connection, desk, record, bill, company, code, reason, *, facts, checks, review, rules=()):
    offers = _offers(connection, desk, bill, company, [code]) if company else []
    said = desk.spelled(connection, reason)
    work.update_record(connection, record, status="held", hold_codes=[code], review_reasons=[said[:300], *review],
                       facts=facts, company_id=company["id"] if company else None,
                       proposal={"bill": bill, **({"rules": list(rules)} if rules else {})},
                       checks={**checks, "offers": offers})
    return {"status": "held", "code": code, "reason": reason}


def _offers(connection, desk, bill, company, codes):
    """The held bill's record-specific writes: a best guess its candidate passes the gate for, or its new supplier."""
    allowed, view, until, offers = hold_actions(codes), desk.view(connection, company), desk.until(company), []
    if "guess" in allowed:
        try:
            check(bill, view, company, until=until)
            offers.append("guess")
        except HoldReason:
            pass
    if "supplier" in allowed and _supplier_plan(bill, view, company, until) is not None:
        offers.append("supplier")
    return offers


def _precedent(connection, desk, company, bound):
    """The review a booking needs, or None, and how many times the client booked this supplier's bills this way.

    "This way" is the same voucher type and expense ledgers, item-wise when the bill is and not otherwise.
    What memory learnt comes first: a booking someone changed in Tally since, or one first written as a best
    guess, waits for a person even when history repeats it; one a person approved is a precedent. Otherwise
    the books' history decides. A bill without a precedent is a first: it goes to review, whatever the
    review mode. The count is what standing approval weighs: a booking seen once may be a one-off.
    """
    if bound.party not in bound.identities:
        return UNPRECEDENTED, 0
    booking = bound.booking
    wanted = set(booking["ledgers"])
    learnt = [row for row in memory.entries(
        connection, desk.run["tenant_id"], desk.run["client_id"], company_ids=desk.part_ids(company),
        kinds=["booking"], subjects=[bound.identities[bound.party]["GUID"]])
        if row["value"]["voucher_type"] == booking["voucher_type"]["NAME"] and wanted <= set(row["value"]["ledgers"])
        and bool(row["value"].get("items")) == booking["items"]]
    statuses = {row["status"] for row in learnt}
    if "demoted" in statuses:
        return DEMOTED, 0
    if "unconfirmed" in statuses and "confirmed" not in statuses:
        return GUESSED_BOOKING, 0
    history = [row for part in desk.parts[company["guid"]]
               for row in mirror.ledger_history(connection, part["id"], part["version"], [bound.party], limit=50)]
    booked = sum(1 for row in history if row["voucher_type"] == booking["voucher_type"]["NAME"]
                 and wanted <= set(row["ledgers"]) and bool(mirror.stock_lines(row["data"])) == booking["items"])
    # A save Minkops made is both a confirmed use and a voucher in the books: the larger count, not their sum.
    seen = max(booked, sum(row["uses"] for row in learnt if row["status"] == "confirmed"))
    if seen:
        return None, seen
    return _departure(connection, desk, company, bound, history), 0


def _standing(record):
    """Whether standing approval may write this proposal without a person: nothing to review, booked so before."""
    return (record["status"] == "proposed" and not record["review_reasons"]
            and (record["checks"] or {}).get("precedents", 0) >= memory.STANDING)


def _departure(connection, desk, company, bound, history):
    """The review a booking that departs from the books needs: what the supplier's last bill was booked to, beside
    what this one is, so a person sees the difference at once; the bare note when the books hold no earlier bill."""
    types = [r["data"] for r in desk.view(connection, company)["masters"]["records"] if r["type"] == "VOUCHERTYPE"]
    bases = {name.casefold(): str(base or "").casefold() for name, base in base_types(types).items()}
    earlier = max((row for row in history if bases.get(row["voucher_type"].casefold()) in PURCHASE_SIDE),
                  key=lambda row: row["date"], default=None)
    if earlier is None:
        return UNPRECEDENTED
    before = ", ".join(sorted(set(earlier["ledgers"]) - {bound.party}))
    itemwise = {True: " item-wise", False: ""}
    return (f"{UNPRECEDENTED} Its last bill, {earlier['reference'] or earlier['date']}, was a "
            f"{earlier['voucher_type']}{itemwise[bool(mirror.stock_lines(earlier['data']))]} to {before}; this one "
            f"is a {bound.booking['voucher_type']['NAME']}{itemwise[bound.booking['items']]} to "
            f"{', '.join(bound.booking['ledgers']) or 'its stock items'}.")


def check_gstin(call, arguments):
    results = []
    for value in arguments["values"]:
        try:
            number = supplier_gst.gstin(value)
            results.append({"value": value, "valid": True, "state": supplier_gst.state_name(number[:2])})
        except ValueError as error:
            results.append({"value": value, "valid": False, "reason": str(error)})
    return {"results": results}


def _nullable(definition):
    return {"anyOf": [{"type": "null"}, definition]}


def choice(*values, null=False):
    """One of these strings, or null when `null`: typed, as a constrained answer needs every enum to be."""
    return {"type": ["string", "null"] if null else "string", "enum": [*values, *([None] if null else [])]}


TEXT = {"type": "string", "minLength": 1, "maxLength": 1000}
LEDGER = reference("A ledger's reference, as find_ledger gives it.")
MONEY = {"type": "number", "exclusiveMinimum": 0}
PRINTED = {"type": ["number", "null"], "exclusiveMinimum": 0}
FIELDS = ("number", "date", "total", "supplier_name", "supplier_gstin", "buyer", "place_of_supply", "taxable", "tax",
          "round_off", "note", "receipt_register", "other")
EVIDENCE = {"type": "array", "maxItems": 40, "description": "Where the bill prints each document value you read.",
            "items": schema({
    "field": choice(*FIELDS), "page": {"type": "integer", "minimum": 1, "maximum": 12},
    "quote": {"type": "string", "minLength": 1, "maxLength": 300}}, ["field", "page", "quote"])}
ADJUSTMENT = schema({
    "kind": choice("advance", "retention", "withholding", "deposit"), "amount": MONEY, "evidence": TEXT},
    ["kind", "amount", "evidence"])
SPLIT_PART = schema({
    "name": {"type": "string", "minLength": 1, "maxLength": 120, "description": "The site, project or department, as printed."},
    "amount": PRINTED, "percent": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 100},
    "evidence": TEXT}, ["name", "amount", "percent", "evidence"])
DOCUMENT = schema({
    "kind": choice("invoice", "credit_note", null=True),
    "number": {"type": ["string", "null"], "maxLength": 100, "description": "The supplier's document number."},
    "date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$", "description": (
        "The issue date, year first as YYYY-MM-DD. Bills print dates day first: 01-Oct-2026 or 01/10/2026 is "
        "2026-10-01. Quote where the bill prints it in evidence.")},
    "total": {**PRINTED, "description": "The gross amount payable for this document, as printed."},
    "supplier_name": {"type": ["string", "null"], "maxLength": 200},
    "supplier_gstin": {"type": ["string", "null"], "maxLength": 20},
    "origin": {**choice("domestic", "foreign", null=True),
               "description": "foreign for an import or a supplier outside India."},
    "buyer_gstin": {"type": ["string", "null"], "maxLength": 20,
                    "description": "The buyer GSTIN the bill is addressed to, as printed."},
    "place_of_supply": {"type": ["string", "null"], "maxLength": 60,
                        "description": "The place of supply as the bill prints it, such as Delhi (07); null if it prints none."},
    "taxable": {**PRINTED, "description": "The printed taxable total; null when the bill prints none."},
    "tax": {"type": ["number", "null"], "minimum": 0, "description": "The printed tax total; null when none is printed."},
    "receipt_register": {"description": "A receipt-register stamp (DMR, GRN or MRN) as printed.", **_nullable(schema({
        "label": {"type": "string", "minLength": 1, "maxLength": 20},
        "number": {"type": "string", "minLength": 1, "maxLength": 40},
        "date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"}}, ["label", "number", "date"]))},
    "adjustments": {**_nullable({"type": "array", "maxItems": 10, "items": ADJUSTMENT}), "description": (
        "What the bill prints as taken off, or held back from, what the supplier is paid: an advance already paid "
        "and adjusted, retention or contractual withholding, or a refundable deposit it charges. Null when it "
        "prints none.")},
    "cost_split": {**_nullable({"type": "array", "maxItems": 20, "items": SPLIT_PART}), "description": (
        "How the bill divides its cost between sites, projects or departments: each part with its amount or its "
        "percentage as printed, never both. Null when it prints no split; a project the bill merely names is none.")}},
    ["kind", "number", "date", "total", "supplier_name", "supplier_gstin", "origin", "buyer_gstin", "place_of_supply",
     "taxable", "tax", "receipt_register", "adjustments", "cost_split"])
LINE = schema({
    "role": choice("expense", "tax", "round_off", "freight", "other_charge", "discount", "tds", "retention",
                   "deposit"),
    "ledger": LEDGER, "side": choice("debit", "credit"),
    "amount": MONEY, "cost_centre": _nullable(reference("A cost centre's reference, as cost_centres gives it.")),
    "tax": _nullable(schema({"head": choice("cgst", "sgst", "igst", "cess"), "rate": MONEY, "taxable": MONEY},
                            ["head", "rate", "taxable"])),
    "tds": _nullable(schema({"section": {"type": "string", "minLength": 2, "maxLength": 10}, "rate": MONEY},
                            ["section", "rate"])),
    "gst_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 100, "description": (
        "For an expense, freight or other charge on a bill taxing its lines at more than one rate: the line's GST "
        "rate as printed (CGST plus SGST, or IGST); 0 for an untaxed line. Otherwise null.")},
    "supply": {**choice("goods", "services", null=True), "description": (
        "For a taxed expense, freight or other charge: whether it supplies goods (HSN) or services (SAC); "
        "otherwise null.")},
    "evidence": {"type": "string", "minLength": 1, "maxLength": 500,
                 "description": "Where the bill prints this line, quoted: such as Page 1: Freight 1,180.00."}},
    ["role", "ledger", "side", "amount", "cost_centre", "tax", "tds", "gst_rate", "supply", "evidence"])
QUANTITY = {"type": "number", "exclusiveMinimum": 0}
ITEM = schema({
    "item": reference("The stock item's reference, as find_stock_item gives it."), "quantity": QUANTITY, "rate": MONEY,
    "amount": MONEY, "ledger": LEDGER,
    "godowns": {"type": "array", "minItems": 1, "maxItems": 10, "items": schema({
        "godown": reference("A godown's reference, as godowns gives it."), "quantity": QUANTITY, "amount": MONEY},
        ["godown", "quantity", "amount"])},
    "evidence": {"type": "string", "minLength": 1, "maxLength": 500}},
    ["item", "quantity", "rate", "amount", "ledger", "godowns", "evidence"])
VOUCHER = schema({
    "family": choice("purchase", "journal", "debit_note"),
    "voucher_type": _nullable(reference("The voucher type's reference, as voucher_types gives it.")),
    "party": schema({"ledger": _nullable(LEDGER), "new_supplier": {
        "type": "boolean", "description": "True only once no ledger is this supplier; the ledger is then null."},
        "evidence": TEXT},
                    ["ledger", "new_supplier", "evidence"]),
    "lines": {"type": "array", "maxItems": 39, "items": LINE, "description": (
        "The voucher's lines besides the supplier's. A ledger carrying several of the bill's lines gets their sum, "
        "except that it takes one line for each cost centre the bill allocates it to, and for each GST rate it is "
        "taxed at.")},
    "items": {**_nullable({"type": "array", "maxItems": 40, "items": ITEM}), "description": (
        "For a purchase the client books item-wise: each item line of the bill, in the stock item's own unit. "
        "Items carry the taxable value their lines print, so they are not expense lines too. Otherwise null.")}},
    ["family", "voucher_type", "party", "lines", "items"])
SUPPLIER = schema({
    **{key: {"type": "string", "maxLength": 250} for key in ("gstin", "registration_type", "state", "state_code",
                                                             "place_of_supply", "pincode")},
    "address": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 250}},
    "evidence": {"type": "array", "maxItems": 20, "items": schema({
        "field": choice("gstin", "registration_type", "state", "place_of_supply", "address"),
        "page": {"type": "integer", "minimum": 1, "maximum": 12},
        "quote": {"type": "string", "minLength": 1, "maxLength": 300}}, ["field", "page", "quote"])}},
    ["gstin", "registration_type", "state", "state_code", "place_of_supply", "address", "pincode", "evidence"])
BILL_SCHEMA = schema({
    "bill": {"type": "integer", "minimum": 1, "maximum": MAX_BILLS}, "document": _nullable(DOCUMENT),
    "company": _nullable(COMPANY), "company_evidence": {"type": ["string", "null"], "maxLength": 1000},
    "voucher": _nullable(VOUCHER), "supplier_details": _nullable(SUPPLIER), "evidence": EVIDENCE,
    "exception": _nullable(schema({"code": choice(*EXCEPTIONS), "detail": TEXT}, ["code", "detail"])),
    "rules": {"type": "array", "maxItems": 10, "items": {"type": "string", "minLength": 36, "maxLength": 36}},
}, ["bill", "document", "company", "company_evidence", "voucher", "supplier_details", "evidence", "exception",
    "rules"])
# A session's final answer: the file's bills, each checked against its company once answered. A bill answered again
# replaces its earlier proposal; one rejected, or not yet answered, goes back to the session.
PROPOSAL = Answer(
    Tool("propose", "The bills of this file, numbered from 1 in the order they appear; `count` is how many bills "
         "the file holds.",
         schema({"count": {"type": "integer", "minimum": 1, "maximum": MAX_BILLS},
                 "bills": {"type": "array", "minItems": 1, "maxItems": MAX_BILLS, "items": BILL_SCHEMA}},
                ["count", "bills"]), propose),
    settled=lambda result: not result.get("still_pending") and all(b["status"] != "rejected" for b in result["bills"]),
    again="Answer again with the bills it rejected or did not receive, each corrected; the bills it accepted or held "
          "stay as they are.")
BILL_TOOLS = {tool.name: tool for tool in (
    Tool("check_gstin", "Whether each value is a valid GSTIN (format, state code and check character), and its state.",
         schema({"values": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 30}}},
                ["values"]), check_gstin),
)}


# --- settling ---------------------------------------------------------------------------

def settle(connection, run, item, outcome):
    if outcome.stopped:
        _hold_pending(connection, item, "run_stopped", hold("run_stopped").reason, refusals=False)
    else:
        _hold_pending(connection, item, "extraction_failed", outcome.error or "No proposal was returned for this bill.")
    _finalize(connection, run, settling=item)


def _printed_key(record):
    """What two readings of one bill must agree on to be the same document: its date and amounts."""
    preview = record["proposal"]["preview"]
    return json.dumps([preview["date"], preview["total"], sorted(line["amount"] for line in preview["lines"])])


def _finalize(connection, run, *, settling):
    """Once no other item is left, write repeated bills once and apply standing approval.

    `settling` is the item whose settle calls this; it finishes in the same transaction.
    """
    run = connection.execute("SELECT * FROM runs WHERE id=%s FOR UPDATE", (run["id"],)).fetchone()
    if connection.execute(
            "SELECT 1 FROM run_items WHERE run_id=%s AND id<>%s AND state IN ('waiting','queued','running') LIMIT 1",
            (run["id"], settling["id"])).fetchone():
        return
    ready = connection.execute(
        "SELECT * FROM run_records WHERE run_id=%s AND kind=%s AND status='proposed' ORDER BY id FOR UPDATE",
        (run["id"], KIND)).fetchall()
    groups = {}
    for record in ready:
        if not record["proposal"].get("repeat_of"):
            groups.setdefault((record["proposal"]["destination_key"], record["proposal"]["identity"]), []).append(record)
    for group in groups.values():
        if len(group) < 2:
            continue
        if len({_printed_key(r) for r in group}) > 1:
            for record in group:
                work.update_record(connection, record, status="held", hold_codes=["source_values_conflict"],
                                   review_reasons=["Selected files print different versions of this bill."])
            continue
        # One reading is written; the copies follow it, whatever ledgers their own sessions chose.
        first, *rest = sorted(group, key=lambda r: (r["facts"]["file"], r["position"]))
        for record in rest:
            work.update_record(connection, record, proposal={**record["proposal"], "repeat_of": str(first["id"])},
                               review_reasons=[f"This bill is also in {first['facts']['file']}; it is entered once."])
    _link_copies(connection, run, ready)
    if (run["config"].get("review_mode") == "only_exceptions"
            and control_state(connection, run["tenant_id"], run["task_id"]) == "active"):
        for record in ready:
            if _standing(record):
                _approve(connection, run, record, actor=run["actor_id"])


def _copy_key(record):
    """One bill as its printed copies show it: buyer, supplier, number, date and total; None for one not read."""
    facts = record["facts"] or {}
    key = [facts.get(field) for field in ("company", "supplier", "number", "date", "total")]
    if None in key:
        return None
    return key[0], mirror.normalized(key[1]), mirror.normalized(key[2]), key[3], key[4]


def _link_copies(connection, run, ready):
    """One bill in several files, not all written once together: each copy names the others.

    Proposed copies of one reading are grouped to be written once above. A held copy has no reading to group by, so
    it and its copies in other files name each other. A proposed copy then waits for a person, since standing
    approval writes only a bill with no review note; and of two held copies, the one a person settles first is
    never entered again from the other.
    """
    held = connection.execute("SELECT * FROM run_records WHERE run_id=%s AND kind=%s AND status='held' "
                              "ORDER BY id FOR UPDATE", (run["id"], KIND)).fetchall()
    settled = {r["id"] for r in held}
    copies = {}
    for record in [*(r for r in ready if r["status"] == "proposed" and r["id"] not in settled), *held]:
        if key := _copy_key(record):
            copies.setdefault(key, []).append(record)
    notes = {}
    for group in copies.values():
        proposed = next((r for r in group if r["status"] == "proposed"), None)
        for record in (r for r in group if r["status"] == "held"):
            others = [r for r in group if r["item_id"] != record["item_id"]]
            if proposed is not None and proposed["item_id"] != record["item_id"]:
                why = (record["review_reasons"] or [hold(record["hold_codes"][0]).reason])[0]
                notes.setdefault(proposed["id"], (proposed, []))[1].append(
                    f"This bill is also in {record['facts']['file']}, held there: {why}"[:300])
                notes.setdefault(record["id"], (record, []))[1].append(
                    f"This bill is also in {proposed['facts']['file']}, where it is proposed; it is entered once.")
            for other in (r for r in others if r["status"] == "held"):
                notes.setdefault(record["id"], (record, []))[1].append(
                    f"This bill is also in {other['facts']['file']}, held there too; it is entered once.")
    for record, added in notes.values():
        fresh = [note for note in dict.fromkeys(added) if note not in record["review_reasons"]]
        if fresh:
            work.update_record(connection, record, review_reasons=[*record["review_reasons"], *fresh])


# --- review and decisions ---------------------------------------------------------------

def _offered(record, run=None):
    """The decisions a bill offers now. One left as is can be read again once Tally is fixed; a stopped run offers
    only Do nothing, since every other decision needs it active."""
    offered = []
    if record["status"] == "proposed":
        offered = ["approve", "nothing"]
    elif record["status"] == "deferred":
        offered = ["retry"]
    elif record["status"] == "held":
        offers = (record["checks"] or {}).get("offers") or []
        offered = [action for action in hold_actions(record["hold_codes"])
                   if action in OFFERED and (action not in ("guess", "supplier") or action in offers)]
    if (run or {}).get("control_state") == "stopped":
        return [action for action in offered if action == "nothing"]
    return offered


def summarize(run, record):
    facts, preview = record["facts"] or {}, (record["proposal"] or {}).get("preview") or {}
    return {key: value for key, value in {
        "id": str(record["id"]), "version": record["version"], "kind": record["kind"], "status": record["status"],
        "file": facts.get("file"), "bill": facts.get("bill"), "supplier": preview.get("party") or facts.get("supplier"),
        "number": facts.get("number"), "date": facts.get("date"), "total": facts.get("total"),
        "company": facts.get("company"), "voucher_type": preview.get("voucher_type"),
        "holds": [{"code": code, "label": hold(code).label, "reason": hold(code).reason_for(BILL)}
                  for code in record["hold_codes"]], "review": record["review_reasons"],
        "actions": [{"action": a, "label": ACTIONS.get(a, "Approve")} for a in _offered(record, run)],
    }.items() if value not in (None, [])}


def detail(connection, run, record):
    proposal = record["proposal"] or {}
    bill = proposal.get("bill") or {}
    supplier = {key: value for key, value in (bill.get("supplier_details") or {}).items() if key != "evidence"}
    return {**summarize(run, record), "facts": record["facts"], "preview": proposal.get("preview"),
            "evidence": bill.get("evidence"), "lines": (bill.get("voucher") or {}).get("lines"),
            "exception": bill.get("exception"), "repeat_of": proposal.get("repeat_of"), "rules": proposal.get("rules"),
            "guess": proposal.get("guess", False), "current": record["current"],
            **({"new_supplier": {"name": (bill.get("document") or {}).get("supplier_name"), **supplier}}
               if "supplier" in _offered(record, run) else {})}


def decide(connection, run, record, action, detail, context):
    if action not in _offered(record, run):
        raise ServiceError("conflict", "That action is not available for this bill now.")
    if action == "nothing":
        work.update_record(connection, record, status="deferred")
        return {"status": "deferred"}
    require_active(connection, run["tenant_id"], run["task_id"])
    actor = context["user"]["id"]
    if action == "retry":
        return _recheck(connection, run, record, actor)
    if action == "supplier":
        return _create_supplier(connection, run, record, actor=actor)
    if action == "guess":
        work.update_record(connection, record, status="proposed", hold_codes=[], review_reasons=[GUESSED],
                           proposal={**record["proposal"], "guess": True})
    elif action == "retry_save":
        work.update_record(connection, record, status="proposed", hold_codes=[], review_reasons=[])
    return _approve(connection, run, record, actor=actor)


def _recheck(connection, run, record, actor):
    """A new attempt of the file's session once its PC has read the books afresh (desk_tools.recheck): this bill and
    the file's bills not yet decided are read again, so a ledger created in Tally since is found."""
    item = connection.execute("SELECT * FROM run_items WHERE id=%s FOR UPDATE", (record["item_id"],)).fetchone()
    if item["state"] == "running":
        raise ServiceError("conflict", "This file is being read now. Recheck it once it finishes.")
    blocker, pcs = desk_tools.recheck(connection, run, actor,
                                      [record["company_id"]] if record["company_id"] else list(run["pins"]))
    if item["state"] in ("done", "failed"):
        work.requeue_item(connection, run["tenant_id"], item["id"], waiting_on=blocker)
    connection.execute(
        """UPDATE run_records SET status='pending', hold_codes='{}',
               review_reasons=CASE WHEN id=%s THEN %s ELSE '{}'::text[] END, proposal=NULL, checks=NULL,
               company_id=NULL, current=NULL, version=version+1, updated_at=now() WHERE id = ANY(%s)""",
        (record["id"], [desk_tools.waiting_note("bill", pcs)],
         [r["id"] for r in _records(connection, item, lock=True) if _open(r) or r["id"] == record["id"]]))
    return {"status": "pending"}


def approve_ready(connection, run, actor):
    """Approve every proposed bill that needs no review, as one Write ready bills action."""
    require_active(connection, run["tenant_id"], run["task_id"])
    ids = [row["id"] for row in connection.execute(
        """SELECT id FROM run_records WHERE run_id=%s AND kind=%s AND status='proposed' AND review_reasons='{}'
           ORDER BY id""", (run["id"], KIND)).fetchall()]
    for record_id in ids:
        # Read each bill as it is now: approving one bill also approves its copies in other files.
        record = connection.execute("SELECT * FROM run_records WHERE id=%s FOR UPDATE", (record_id,)).fetchone()
        if record["status"] == "proposed" and not record["review_reasons"]:
            _approve(connection, run, record, actor=actor)
    approved = connection.execute("SELECT count(*) AS n FROM run_records WHERE id = ANY(%s) AND status IN "
                                  "('approved','writing')", (ids,)).fetchone()["n"]
    work.refresh(connection, run["tenant_id"], run["id"], describe=describe)
    return {"approved": approved}


def _destination(connection, run, record):
    """The run's desk and the company part the bill is entered into."""
    desk = Desk(connection, run)
    guid = connection.execute("SELECT guid FROM companies WHERE id=%s", (record["company_id"],)).fetchone()["guid"]
    return desk, desk.company(guid, on=_iso((record["proposal"]["bill"].get("document") or {}).get("date")))


def _approve(connection, run, record, *, actor):
    """One approval writes once: a bill repeated in another file approves the record that writes it."""
    leader_id = record["proposal"].get("repeat_of")
    if leader_id:
        leader = connection.execute("SELECT * FROM run_records WHERE id=%s FOR UPDATE", (leader_id,)).fetchone()
        if leader["status"] == "proposed":
            work.update_record(connection, record, status="approved")
            _approve(connection, run, leader, actor=actor)
            return {"status": "approved"}
        if leader["status"] in ("approved", "writing"):
            work.update_record(connection, record, status="approved")
            return {"status": "approved"}
        if leader["status"] in ("saved", "duplicate"):
            work.update_record(connection, record, status="duplicate", current=leader["current"])
            return {"status": "duplicate"}
        # The copy it repeated was not written: this one is written on its own.
        work.update_record(connection, record, proposal={key: value for key, value in record["proposal"].items()
                                                         if key != "repeat_of"})
    desk, company = _destination(connection, run, record)
    try:
        bound = check(record["proposal"]["bill"], desk.view(connection, company), company,
                      created=record["proposal"].get("created", ()), until=desk.until(company))
    except HoldReason as refusal:
        work.update_record(connection, record, status="held", hold_codes=[refusal.code],
                           review_reasons=[str(refusal)[:300]])
        return {"status": "held"}
    # Duplicates are sought where the company types invoice numbers; until that is settled, in both places.
    fields = (practice.settled(connection, company, "invoice_number_field") or {}).get("fields")
    plan = {**bound.native_plan(narration_token(run["tenant_id"], bound.destination_key, bound.identity),
                                number_fields=tuple(fields or ("REFERENCE", "NARRATION")),
                                note=_register_note(connection, company, record["proposal"]["bill"])),
            "destination_key": bound.destination_key}
    row = connection.execute("SELECT * FROM companies WHERE id=%s", (record["company_id"],)).fetchone()
    if not writes.request(connection, run, record, plan, row, actor=actor):
        work.update_record(connection, record, status="held", hold_codes=["save_waiting"],
                           review_reasons=["Another approved run is saving this bill. Retry once it finishes."])
        return {"status": "held"}
    # The booking the save teaches, as the plan was bound from it (memory.learn_booking).
    work.update_record(connection, record, status="writing", proposal={**record["proposal"], "booking": bound.booking})
    for follower in connection.execute(
            "SELECT * FROM run_records WHERE run_id=%s AND status='proposed' AND proposal->>'repeat_of'=%s FOR UPDATE",
            (run["id"], str(record["id"]))).fetchall():
        work.update_record(connection, follower, status="approved")
    return {"status": "writing"}


def _register_note(connection, company, bill):
    """The bill's receipt-register stamp, for a company that records it in the purchase narration."""
    register = (bill.get("document") or {}).get("receipt_register")
    if not register or (practice.settled(connection, company, "receipt_register") or {}).get("recorded_in") != (
            "narration"):
        return None
    return f"{register['label']} {register['number']}" + (f" of {register['date']}" if register["date"] else "")


def _repropose(connection, run, record, bill, *, review, created=(), precedent=False):
    """Check a held bill's reading again and propose it; False when it no longer passes.

    `precedent` asks whether the booking needs review again, as after a practice answer.
    """
    desk, company = _destination(connection, run, record)
    try:
        bound = check(bill, desk.view(connection, company), company, created=created, until=desk.until(company))
    except HoldReason as refusal:
        work.update_record(connection, record, status="held", hold_codes=[refusal.code],
                           review_reasons=[str(refusal)[:300]])
        return False
    waits = _waits(connection, company, bill, bound)
    if waits:
        code, reason, probe = waits
        work.update_record(connection, record, status="held", hold_codes=[code], review_reasons=[reason, *review],
                           checks={**(record["checks"] or {}), "practice": probe,
                                   **({"final": True} if code != "practice_question" else {})})
        return False
    review = [*review, *[note for note in bound.notes if note not in review]]
    checks = {**(record["checks"] or {}), "offers": []}
    if precedent:
        note, checks["precedents"] = _precedent(connection, desk, company, bound)
        review = [*review, *([note] if note else [])]
    kept = {key: record["proposal"][key] for key in ("rules",) if record["proposal"].get(key)}
    work.update_record(connection, record, status="proposed", hold_codes=[], review_reasons=review,
                       checks=checks,
                       proposal=_proposal(bill, bound, **kept, **({"created": list(created)} if created else {})))
    return True


def practice_settled(connection, tenant_id, company_id, probe):
    """A practice question was answered: the company's bills waiting on it are checked again, in runs still going."""
    for record in connection.execute(
            """SELECT r.* FROM run_records r JOIN runs n ON n.tenant_id=r.tenant_id AND n.id=r.run_id
               JOIN tasks t ON t.tenant_id=n.tenant_id AND t.id=n.task_id
               WHERE r.tenant_id=%s AND r.company_id=%s AND r.kind=%s AND r.status='held'
                 AND r.hold_codes='{practice_question}' AND r.checks->>'practice'=%s AND t.control_state<>'stopped'
               ORDER BY r.id FOR UPDATE OF r""", (tenant_id, company_id, KIND, probe)).fetchall():
        run = work.get_run(connection, tenant_id, record["run_id"])
        # The hold's own reason and any earlier booking review are restated by the check.
        review = [reason for reason in record["review_reasons"][1:] if not reason.startswith(BOOKING_REVIEWS)]
        if (_repropose(connection, run, record, record["proposal"]["bill"], review=review, precedent=True)
                and run["config"].get("review_mode") == "only_exceptions" and not review
                and control_state(connection, tenant_id, run["task_id"]) == "active"):
            proposed = work.get_record(connection, tenant_id, record["id"], lock=True)
            if _standing(proposed):
                _approve(connection, run, proposed, actor=run["actor_id"])
        work.refresh(connection, tenant_id, run["id"], describe=describe)


# --- new suppliers ----------------------------------------------------------------------

def _supplier_plan(bill, view, company, until):
    """The supplier ledger a person may create for this bill, or None when it cannot be created safely.

    The bill must name a new supplier with printed evidence and pass every
    check once that supplier exists; a GST bill's ledger copies its company's
    GST creditor template (supplier_gst.creation_plan).
    """
    party = (bill.get("voucher") or {}).get("party") or {}
    if party.get("ledger_guid") is not None or party.get("new_supplier") is not True:
        return None
    if not any(e["field"] == "supplier_name" and e["quote"].strip() for e in bill.get("evidence") or []):
        return None
    vendor = ((bill.get("document") or {}).get("supplier_name") or "").strip()
    if any(record["type"] == "LEDGER" and mirror.normalized(supplier_gst.scalar(
            record["data"].get("@_NAME") or record["data"].get("NAME"))) == mirror.normalized(vendor)
           for record in view["masters"]["records"]):
        return None  # A ledger already has this name: the supplier is not missing, only unmatched.
    try:
        bound = check(bill, view, company, until=until, assume_new_supplier=True)
        tax = sum(ln["amount_cents"] for ln, item in zip(bound.lines[1:], bill["voucher"]["lines"], strict=True)
                  if item["role"] == "tax")
        gst = supplier_gst.creation_plan(bill.get("supplier_details"), view, tax=tax, issued=bill["document"]["date"])
    except ValueError:
        return None
    return {"kind": "supplier", "company": company["name"], "company_guid": company["guid"], "vendor": vendor,
            "gst_supplier": gst, "destination_key": f"supplier:{company['guid']}",
            "identity": {"hash": gst["gstin"] if gst else mirror.normalized(vendor)}}


def _create_supplier(connection, run, record, *, actor):
    desk, company = _destination(connection, run, record)
    plan = _supplier_plan(record["proposal"]["bill"], desk.view(connection, company), company, desk.until(company))
    if plan is None:
        raise ServiceError("conflict", "This supplier can no longer be created from the bill's details.")
    row = connection.execute("SELECT * FROM companies WHERE id=%s", (record["company_id"],)).fetchone()
    if not writes.request(connection, run, record, plan, row, actor=actor):
        raise ServiceError("conflict", "This supplier is being created for another bill. Once that finishes, its bills "
                                       "here are checked again with it.")
    work.update_record(connection, record, status="writing")
    return {"status": "writing"}


def _created_master(plan, receipt):
    """The created supplier's identity, verified from the companion's readback, or why it cannot be trusted."""
    if receipt.get("outcome") == "attention":
        return None, (str(receipt.get("message") or "") or "The supplier could not be created and verified in Tally.")
    if receipt.get("company_guid") != plan["company_guid"]:
        return None, "Tally answered for another company, so the supplier was not verified."
    named = [ledger for ledger in receipt.get("ledgers") or [] if isinstance(ledger, dict) and mirror.normalized(
        supplier_gst.scalar(ledger.get("@_NAME") or ledger.get("NAME"))) == mirror.normalized(plan["vendor"])]
    if len(named) != 1:
        return None, "Tally does not show exactly one ledger with this supplier's name."
    master = {"@_NAME": supplier_gst.scalar(named[0].get("@_NAME") or named[0].get("NAME")),
              **{key: supplier_gst.scalar(named[0].get(key)) for key in ("GUID", "PARENT", "ALTERID")}}
    if not master["GUID"] or master["PARENT"] != "Sundry Creditors":
        return None, f"The ledger {master['@_NAME']} in Tally is not a supplier under Sundry Creditors."
    supplier = receipt.get("supplier")
    if plan["gst_supplier"] and not (isinstance(supplier, dict) and supplier_gst.scalar(supplier.get("GUID")) ==
                                     master["GUID"] and supplier_gst.verified_supplier(supplier, plan["gst_supplier"])):
        return None, "The supplier's GST details in Tally differ from the bill. Review the ledger there."
    return master, None


def _supplier_created(connection, run, record, write, receipt):
    """A verified new supplier: its bills in this run are checked again with it, and the approved one is written."""
    plan = write["plan"]
    master, problem = _created_master(plan, receipt)
    if problem:
        work.update_record(connection, record, status="held", hold_codes=["supplier_missing"],
                           review_reasons=[problem[:300]])
        return {"verified": False, "outcome": "held"}
    created = {"type": "LEDGER", "data": master}
    desk, company = _destination(connection, run, record)
    view, until = desk.view(connection, company), desk.until(company)
    for other in connection.execute(
            """SELECT * FROM run_records WHERE run_id=%s AND company_id=%s AND id<>%s AND status='held'
                   AND hold_codes='{supplier_missing}' FOR UPDATE""",
            (run["id"], record["company_id"], record["id"])).fetchall():
        found = _supplier_plan(other["proposal"]["bill"], view, company, until)
        if found and found["identity"] == plan["identity"]:
            _with_supplier(connection, run, other, created, review=[UNPRECEDENTED])
    if _with_supplier(connection, run, record, created, review=[]):
        _approve(connection, run, record, actor=run["actor_id"])
    return {"verified": True, "outcome": "saved"}


def _with_supplier(connection, run, record, created, *, review):
    """Propose a bill again with its newly created supplier as the party; False when it no longer passes."""
    bill = record["proposal"]["bill"]
    bill = {**bill, "voucher": {**bill["voucher"], "party": {
        "ledger_guid": created["data"]["GUID"], "new_supplier": False,
        "evidence": "Created by Minkops on a person's approval and verified in Tally."}}}
    return _repropose(connection, run, record, bill, review=review, created=[created])


# --- receipts and stops -----------------------------------------------------------------

def written(connection, run, record, write, receipt):
    """A receipt from the companion: a created supplier, a verified bill, or a hold."""
    if write["plan"].get("kind") == "supplier":
        return _supplier_created(connection, run, record, write, receipt)
    outcome = receipt.get("outcome")
    if outcome not in ("saved", "duplicate", "correction", "attention"):
        raise ServiceError("invalid", "Invalid Tally write receipt.")
    current = None
    if outcome != "attention":
        try:
            current = observed_bill(write["plan"], outcome, receipt.get("current"),
                                    identity=write["plan"]["identity"]["hash"])
        except ValueError as error:
            raise ServiceError("invalid", str(error)) from error
    if outcome in ("saved", "duplicate"):
        guessed = bool(record["proposal"].get("guess"))
        returns = [note for note in [_returns_note(write["plan"], current)] if outcome == "saved" and note]
        work.update_record(connection, record, status=outcome, current=current, hold_codes=[],
                           review_reasons=[*([GUESSED] if guessed else []), *returns])
        # A verified save a person approved is how this supplier's bills are booked.
        memory.learn_booking(connection, run, record, write["plan"], current["guid"],
                             actor_id=memory.approver(connection, run, record), guessed=guessed)
        follow = {"status": "duplicate", "current": current, "hold_codes": [], "review_reasons": []}
    else:
        if outcome == "correction":
            code, reason = "save_held", correction_reason(write["plan"], receipt["current"])
        else:
            code = receipt.get("hold") if receipt.get("hold") in SAVE_HOLDS else "save_held"
            reason = str(receipt.get("message") or "") or hold(code).reason_for(BILL)
        work.update_record(connection, record, status="held", hold_codes=[code], review_reasons=[reason[:300]],
                           current=current)
        follow = {"status": "held", "hold_codes": [code], "review_reasons": [reason[:300]]}
    for follower in connection.execute(
            "SELECT * FROM run_records WHERE run_id=%s AND status='approved' AND proposal->>'repeat_of'=%s FOR UPDATE",
            (run["id"], str(record["id"]))).fetchall():
        work.update_record(connection, follower, **follow)
    return {"verified": outcome in ("saved", "duplicate"),
            "outcome": outcome if outcome in ("saved", "duplicate") else "held"}


# How a saved bill stands in Tally's GST returns, when it is not counted, for the person who completes it there.
RETURNS_NOTES = {
    "uncertain": "Saved in Tally, but Tally's GST returns list it under Uncertain Transactions, so its tax is not "
                 "claimed yet. Complete its GST details in Tally from GSTR-3B's uncertain transactions.",
    "excluded": "Saved in Tally, but Tally excludes it from its GST returns, so its tax is not claimed. Check its GST "
                "details in Tally.",
    "not_applicable": "Saved in Tally, but Tally treats it as outside GST, so its tax is not claimed. Check that its "
                      "purchase ledger has GST applicable in Tally.",
    "unknown": "Saved in Tally, but Tally did not say whether its GST returns include it. Check it in GSTR-3B.",
}


def _returns_note(plan, current):
    """Why a bill saved for a GST-registered company is not in Tally's returns yet, or None.

    Tally judges the voucher against its own masters, as it stores it: item-wise bills whose items carry no GST
    details, or a supplier ledger set up otherwise, can leave a sound entry out of the returns.
    """
    if not plan.get("gst"):
        return None
    return RETURNS_NOTES.get((current.get("gst") or {}).get("status", "unknown"))


def stopped(connection, run):
    """Stop: unstarted items are cancelled, unsaved bills hold, and pending writes are withdrawn."""
    work.cancel(connection, run["tenant_id"], run["id"])
    withdrawn = writes.cancel(connection, run)
    connection.execute(
        """UPDATE run_records SET status='held', hold_codes='{run_stopped}', review_reasons=%s, version=version+1,
           updated_at=now() WHERE run_id=%s AND (status IN ('pending','proposed','approved')
               OR (status='writing' AND id = ANY(%s)))""",
        ([hold("run_stopped").reason_for(BILL)], run["id"], withdrawn))


describe = partial(work.describe_run, wording=work.Wording(
    input=("file", "files"), entry=("bill", "bills"), destination="Tally",
    preparing="Refreshing the Tally copy on your PC.", failed="The bills could not be read. Recheck them or start a new run."))


class BillEntry:
    """The `desk.bill` handler: the hooks lanes, the runs API and native writes call."""

    launch = staticmethod(launch)
    session = staticmethod(session)
    settle = staticmethod(settle)
    describe = staticmethod(describe)
    summarize = staticmethod(summarize)
    detail = staticmethod(detail)
    decide = staticmethod(decide)
    approve_ready = staticmethod(approve_ready)
    written = staticmethod(written)
    stopped = staticmethod(stopped)


HANDLER = BillEntry()
