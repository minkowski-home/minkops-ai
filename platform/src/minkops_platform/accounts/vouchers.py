"""Accounting vouchers at the native boundary (plan protocol 5).

A v5 plan is the one contract every voucher family shares: a header and
balanced ledger lines (connectors/desktop/src/voucher.js writes it). Stored
plans keep the format they were approved in; a protocol-5 companion receives
them upgraded here, and its receipts are verified against that upgrade and
returned in the observation shape the stored run already uses. Upgrading is
lossless or refused: a plan without pinned native identities is served as is.
"""

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

FORMAT = 5
# Purchase documents may already be booked as Journals; never enter them twice.
BILL_FAMILIES = ["purchase", "journal"]
NARRATION_TAG = "statement"


def normalized(value):
    return str(value).strip().casefold()


def invoice_year(issued):
    """The Indian April–March year that numbers a domestic supplier's invoices.

    Invoice serials are unique within this year (CGST Rule 46), so a supplier
    and number identify one document inside it, whatever the buyer's books use.
    """
    return issued.year if issued.month >= 4 else issued.year - 1


def invoice_window(issued):
    year = invoice_year(issued)
    return {"from": f"{year}-04-01", "to": f"{year + 1}-03-31"}


def document_identity(party, number, issued, *, series="invoice"):
    """Business identity of a supplier document.

    The invoice series hashes exactly as Minkops always has, so vouchers saved
    before protocol 5 keep their remote IDs and pending-write reservations.
    """
    parts = [normalized(party), normalized(number), invoice_year(issued)]
    if series != "invoice":
        parts = [series, *parts]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _cents(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        return None
    return int(amount * 100)


def _line(ledger, side, cents, allocation=None):
    return {"ledger": ledger, "side": side, "amount_cents": cents, "allocation": allocation}


def _signed(line):
    return line["amount_cents"] if line["side"] == "credit" else -line["amount_cents"]


def _pinned(ledgers, lines):
    """Every line ledger must carry its discovered GUID; protocol 5 rechecks it."""
    found = {line["ledger"]: (ledgers or {}).get(line["ledger"]) for line in lines}
    if any(not isinstance(v, dict) or not v.get("GUID") for v in found.values()):
        return None
    return {name: {k: v[k] for k in ("GUID", "PARENT", "ALTERID") if v.get(k) is not None} for name, v in found.items()}


def _bill(plan, identity):
    data, refs = plan.get("data") or {}, plan.get("references") or {}
    voucher_type = refs.get("voucher_type") or {}
    if data.get("cost_code") or not refs.get("company_guid") or not voucher_type.get("GUID"):
        return None
    taxes = plan.get("tax_allocations")
    if taxes is None:
        taxes = [{"ledger": data.get("tax_ledger"), "amount": data["tax"]}] if data.get("tax") else []
    lines = [_line(data.get("vendor"), "credit", _cents(data.get("total"))),
             _line(data.get("purchase_ledger"), "debit", _cents(data.get("subtotal"))),
             *(_line(t.get("ledger"), "debit", _cents(t.get("amount"))) for t in taxes)]
    if any(not isinstance(ln["ledger"], str) or not ln["amount_cents"] or ln["amount_cents"] < 0 for ln in lines):
        return None
    ledgers = _pinned(refs.get("ledgers"), lines)
    if ledgers is None:
        return None
    issued = date.fromisoformat(data["date"])
    number = data["invoice_number"]
    expected = plan.get("expected")
    return {
        "family": "purchase", "fence": "retry_after_read",
        "voucher_type": {"NAME": voucher_type["NAME"], "GUID": voucher_type["GUID"]},
        "company_guid": refs["company_guid"],
        "header": {"date": data["date"], "reference": number, "party_ledger": data["vendor"],
                   "narration": f"Minkops reviewed bill {number}", "tag": None},
        "lines": lines, "references": {"company_guid": refs["company_guid"], "ledgers": ledgers},
        "duplicate": {"strategy": "document", "families": BILL_FAMILIES, "party_ledger": data["vendor"],
                      "number": number, "number_fields": ["REFERENCE"], "window": invoice_window(issued)},
        "expected": {"guid": expected["guid"], "fingerprint": expected["fingerprint"]} if expected else None,
        "identity": {"version": 2, "series": "invoice", "rule": "in_invoice_year", "hash": identity},
    }


def _statement(plan, identity, distinct):
    data, refs, allocation = plan["data"], plan.get("references") or {}, plan.get("allocation")
    amount = data.get("amount_cents")
    if type(amount) is not int or not amount or not refs.get("company_guid") or not plan.get("voucher_type", {}).get("GUID"):
        return None
    bank_side, counter_side = ("credit", "debit") if amount < 0 else ("debit", "credit")
    if allocation is not None:
        allocation = {k: allocation.get(k) for k in ("category", "category_guid", "centre", "centre_guid")}
    lines = [_line(data["bank_ledger"], bank_side, abs(amount)), _line(data["counter_ledger"], counter_side, abs(amount), allocation)]
    ledgers = _pinned(refs.get("ledgers"), lines)
    if ledgers is None:
        return None
    return {
        "family": "payment" if amount < 0 else "receipt", "fence": "strict",
        "voucher_type": {"NAME": plan["voucher_type"]["NAME"], "GUID": plan["voucher_type"]["GUID"]},
        "company_guid": plan["company_guid"],
        # Statement vouchers have always used the source reference, else their remote ID.
        "header": {"date": data["date"], "reference": data.get("reference") or plan["remote_id"], "party_ledger": None,
                   "narration": str(data.get("narration") or "")[:500], "tag": NARRATION_TAG},
        "lines": lines, "references": {"company_guid": refs["company_guid"], "ledgers": ledgers},
        "duplicate": {"strategy": "tag", "window": {"from": data["date"], "to": data["date"]},
                      "match": {"ledger": data["bank_ledger"], "side": bank_side, "amount_cents": abs(amount)},
                      "distinct": sorted(set(distinct))},
        "expected": None,
        "identity": {"version": 2, "series": "statement", "rule": "statement_row", "hash": identity},
    }


def upgrade(plan, *, identity, distinct=()):
    """The v5 form of a stored plan, or None to serve the stored plan unchanged.

    `distinct` lists remote IDs of other rows the server proved to be separate
    transactions (statement siblings), so equal same-day amounts do not hold.
    """
    version = plan.get("format_version", 1)
    if version == FORMAT:
        return plan
    if version in (1, 2, 3) and "data" in plan and "invoice_number" in plan["data"]:
        body = _bill(plan, identity)
    elif version == 4:
        body = _statement(plan, identity, distinct)
    else:
        body = None
    if body is None:
        return None
    return {"format_version": FORMAT, "operation": plan.get("operation", "append"), "company": plan["company"],
            "port": plan.get("port") or 9000, "remote_id": plan["remote_id"], **body}


_VIEW = {"guid", "master_id", "date", "voucher_type", "family", "reference", "number", "narration", "party_ledger",
         "tag", "lines", "allocations", "fingerprint"}


def _current(current):
    """Structural checks on a reported voucher; values are data, never trusted."""
    if not isinstance(current, dict) or set(current) != _VIEW:
        raise ValueError("Tally receipt must contain an observed voucher.")
    if (any(not isinstance(current[k], str) for k in _VIEW - {"lines", "allocations", "tag"})
            or any(len(current[k]) > 500 for k in _VIEW - {"lines", "allocations", "tag", "narration"})
            or len(current["narration"]) > 5000 or (current["tag"] is not None and not isinstance(current["tag"], str))):
        raise ValueError("Invalid observed voucher.")
    if not current["guid"] or not current["master_id"] or not re.fullmatch(r"\d{8}", current["date"]) or not current["fingerprint"]:
        raise ValueError("Invalid observed voucher.")
    if not isinstance(current["lines"], list) or not 1 <= len(current["lines"]) <= 100 or any(
            not isinstance(e, dict) or set(e) != {"ledger", "amount_cents"} or not isinstance(e["ledger"], str)
            or type(e["amount_cents"]) is not int for e in current["lines"]):
        raise ValueError("Invalid ledger readback.")
    if not isinstance(current["allocations"], list) or any(
            not isinstance(a, dict) or set(a) != {"ledger", "category", "centre", "amount_cents"}
            or type(a["amount_cents"]) is not int for a in current["allocations"]):
        raise ValueError("Invalid allocation readback.")
    return current


def _lines(plan):
    return sorted(({"ledger": ln["ledger"], "amount_cents": _signed(ln)} for ln in plan["lines"]),
                  key=lambda e: (e["ledger"], e["amount_cents"]))


def _allocations(plan):
    return sorted(({"ledger": ln["ledger"], "category": ln["allocation"]["category"], "centre": ln["allocation"]["centre"],
                    "amount_cents": _signed(ln)} for ln in plan["lines"] if ln["allocation"]),
                  key=lambda a: (a["ledger"], a["amount_cents"]))


def _exact(plan, current):
    if (current["date"] != plan["header"]["date"].replace("-", "")
            or sorted(current["lines"], key=lambda e: (e["ledger"], e["amount_cents"])) != _lines(plan)
            or sorted(current["allocations"], key=lambda a: (a["ledger"], a["amount_cents"])) != _allocations(plan)):
        raise ValueError("Tally readback differs from the approved amounts or ledgers.")


def _entries(current):
    return [{"ledger": e["ledger"], "amount": e["amount_cents"]} for e in current["lines"]]


def _number_in(current, duplicate):
    """The document number the companion matched, found again independently."""
    number = normalized(duplicate["number"])
    for field in duplicate["number_fields"]:
        if field == "REFERENCE" and normalized(current["reference"]) == number:
            return current["reference"]
        if field == "VOUCHERNUMBER" and normalized(current["number"]) == number:
            return current["number"]
        if field == "NARRATION" and re.search(rf"(?<![a-z0-9]){re.escape(number)}(?![a-z0-9])", normalized(current["narration"])):
            return duplicate["number"]
    return None


def observed_bill(plan, outcome, current, *, identity):
    """A v5 bill receipt as the stored observation (`record["current"]`).

    Every outcome must observe the approved document's identity; saved and
    duplicate outcomes must equal the approved voucher exactly.
    """
    current = _current(current)
    number = _number_in(current, plan["duplicate"])
    try:
        issued = date.fromisoformat(f"{current['date'][:4]}-{current['date'][4:6]}-{current['date'][6:]}")
        same = number is not None and document_identity(current["party_ledger"], number, issued) == identity
    except ValueError:
        same = False
    if not same or current["family"] not in plan["duplicate"]["families"]:
        raise ValueError("Readback belongs to a different bill.")
    if outcome in ("saved", "duplicate"):
        _exact(plan, current)
        if outcome == "saved":
            expected = plan.get("expected")
            if expected and current["guid"] != expected["guid"]:
                raise ValueError("Tally returned a different voucher identifier.")
            # An alteration keeps the existing voucher's own type; a new voucher uses the run's.
            if not expected and normalized(current["voucher_type"]) != normalized(plan["voucher_type"]["NAME"]):
                raise ValueError("Tally saved the bill under a different voucher type.")
    return {"master_id": current["master_id"], "guid": current["guid"], "date": current["date"],
            "invoice_number": number, "vendor": current["party_ledger"], "voucher_type": current["voucher_type"],
            "entries": _entries(current), "fingerprint": current["fingerprint"]}


def observed_statement(plan, stored, current):
    """A verified v5 statement receipt as the stored row observation."""
    current = _current(current)
    if current["tag"] != plan["remote_id"] or current["voucher_type"] != plan["voucher_type"]["NAME"]:
        raise ValueError("Native statement readback differs from the approved manifest.")
    _exact(plan, current)
    return {"guid": current["guid"], "master_id": current["master_id"], "fingerprint": current["fingerprint"],
            "date": current["date"], "voucher_type": current["voucher_type"], "tag": current["tag"],
            "entries": _entries(current), "allocation": stored.get("allocation")}


def observed_document(current, target):
    """A v5 refresh observation of a bill as the stored observation shape.

    Returns None when the report is malformed or names another document, so the
    attention check treats it as unresolved rather than trusting the companion.
    """
    try:
        current = _current(current)
    except ValueError:
        return None
    duplicate = {"number": target.get("invoice_number") or "", "number_fields": ["REFERENCE"]}
    number = _number_in(current, duplicate)
    if number is None or normalized(current["party_ledger"]) != normalized(target.get("vendor") or ""):
        return None
    return {"master_id": current["master_id"], "guid": current["guid"], "date": current["date"],
            "invoice_number": target["invoice_number"], "vendor": current["party_ledger"],
            "voucher_type": current["voucher_type"], "entries": _entries(current), "fingerprint": current["fingerprint"]}
