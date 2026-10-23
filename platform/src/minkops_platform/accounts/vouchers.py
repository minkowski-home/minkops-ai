"""Accounting vouchers at the native boundary (plan protocol 5).

A v5 plan is the one contract every voucher family shares: a header and
balanced ledger lines (connectors/desktop/src/voucher.js writes it). Bills and
statement rows are planned in it directly, a companion executes exactly the
stored plan, and its receipt is verified against that plan.
"""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

from . import gst
from .mirror import text
from .voucher_types import base_types

# Plan protocol 6 adds a line's bill references to protocol 5; a companion that executes 6 executes 5.
# The newest plan protocol this server writes. A plan states the lowest it needs (plan_format), so a companion that
# writes protocol 6 keeps writing every voucher that needs nothing newer.
FORMAT = 7
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


def narration_token(tenant_id, destination_key, identity):
    """The remote ID a voucher carries in Tally, as `[Minkops <tag>:<token>]`.

    It includes the tenant, so a fresh tenant can never mistake an earlier
    tenant's tagged voucher for its own; the writer's same-date, same-amount
    rule still holds such a voucher as possibly existing.
    """
    return str(uuid5(NAMESPACE_URL, f"minkops:{tenant_id}:{destination_key}:{identity}"))


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


def plan_format(lines):
    """Protocol 7 for a line split across cost centres or a ledger on several lines; 6 for everything else."""
    repeated = len({ln["ledger"] for ln in lines}) < len(lines)
    return 7 if repeated or any(ln.get("allocations") for ln in lines) else 6


def line_allocations(line):
    """A plan line's cost allocations, each with its share of the line."""
    if line.get("allocations"):
        return line["allocations"]
    return [{**line["allocation"], "amount_cents": line["amount_cents"]}] if line.get("allocation") else []


def _signed(line):
    return line["amount_cents"] if line["side"] == "credit" else -line["amount_cents"]


def statement_voucher(resolved, *, remote_id, identity, distinct=(), counterpart=False, legs=None):
    """A native Payment, Receipt or Contra from a routed statement row.

    `lines` (several counter lines) split the bank amount exactly; a Contra moves
    it to another own bank or cash ledger. The counter line carries the bills it
    settles (`bills`, protocol 6). A paired Contra (`legs`) is written once for
    both statement rows; a lone leg first looks for the transfer its other leg
    may already have entered (`counterpart`).
    """
    data, amount = resolved["data"], resolved["data"]["amount_cents"]
    bank_side, counter_side = ("credit", "debit") if amount < 0 else ("debit", "credit")

    def allocation(a):
        return {k: a[k] for k in ("category", "category_guid", "centre", "centre_guid")} if a else None
    counters = [_line(ln["ledger"], counter_side, ln["amount_cents"], allocation(ln["allocation"])) for ln in resolved["lines"]] \
        if resolved.get("lines") else [_line(data["counter_ledger"], counter_side, abs(amount), allocation(resolved.get("allocation")))]
    if resolved.get("bills"):
        counters[0] = {**counters[0], "bills": resolved["bills"]}
    ledgers = {**resolved["references"]["ledgers"], **{ln["ledger"]: ln["identity"] for ln in resolved.get("lines") or []}}
    window = {"from": data["date"], "to": data["date"]}
    if counterpart:
        issued = date.fromisoformat(data["date"])
        window = {"from": (issued - timedelta(days=3)).isoformat(), "to": (issued + timedelta(days=3)).isoformat()}
    return {
        "format_version": plan_format([_line(data["bank_ledger"], bank_side, abs(amount)), *counters]),
        "family": resolved.get("family") or ("payment" if amount < 0 else "receipt"),
        "fence": "strict",
        "operation": "append", "company": resolved["company"], "company_guid": resolved["company_guid"],
        "port": resolved.get("port") or 9000, "remote_id": remote_id,
        "voucher_type": {"NAME": resolved["voucher_type"]["NAME"], "GUID": resolved["voucher_type"]["GUID"]},
        "header": {"date": data["date"], "reference": data.get("reference") or remote_id, "party_ledger": None,
                   "narration": str(data.get("narration") or "")[:500], "tag": NARRATION_TAG},
        "lines": [_line(data["bank_ledger"], bank_side, abs(amount)), *counters],
        "references": {"company_guid": resolved["company_guid"], "ledgers": {k: {f: v[f] for f in ("GUID", "PARENT", "ALTERID") if v.get(f)}
                                                                              for k, v in ledgers.items()}},
        "duplicate": {"strategy": "counterpart" if counterpart else "tag", "window": window,
                      "match": {"ledger": data["bank_ledger"], "side": bank_side, "amount_cents": abs(amount)},
                      "distinct": sorted(set(distinct))},
        "expected": None,
        "identity": {"version": 2, "series": "statement", "rule": "statement_row" if not legs else "transfer_pair",
                     "hash": identity, **({"legs": legs} if legs else {})},
    }


_VIEW = {"guid", "master_id", "date", "voucher_type", "family", "reference", "number", "narration", "party_ledger",
         "tag", "lines", "allocations", "bills", "inventory", "fingerprint"}
_LISTS = {"lines", "allocations", "bills", "inventory"}
# What a companion from 0.11.0 reads back of a voucher's GST: what it states, and Tally's verdict for its returns.
_GST = {"party_gstin", "registration_type", "state", "country", "place_of_supply", "company_gstin", "status"}
GST_STATUSES = ("included", "uncertain", "excluded", "not_applicable", "unknown")
BILL_TYPES = ("New Ref", "Agst Ref", "Advance", "On Account")


def _current(current):
    """Structural checks on a reported voucher; values are data, never trusted."""
    if not isinstance(current, dict) or set(current) - {"gst"} != _VIEW:
        raise ValueError("Tally receipt must contain an observed voucher.")
    gst_view = current.get("gst")
    if "gst" in current and (not isinstance(gst_view, dict) or set(gst_view) != _GST
                             or any(not isinstance(v, str) or len(v) > 100 for v in gst_view.values())
                             or gst_view["status"] not in GST_STATUSES):
        raise ValueError("Invalid GST readback.")
    if (any(not isinstance(current[k], str) for k in _VIEW - _LISTS - {"tag"})
            or any(len(current[k]) > 500 for k in _VIEW - _LISTS - {"tag", "narration"})
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
    if not isinstance(current["bills"], list) or any(
            not isinstance(b, dict) or set(b) != {"ledger", "name", "type", "amount_cents"} or b["type"] not in BILL_TYPES
            or not (b["name"] is None or isinstance(b["name"], str)) or type(b["amount_cents"]) is not int
            for b in current["bills"]):
        raise ValueError("Invalid bill reference readback.")
    if not isinstance(current["inventory"], list) or any(
            not isinstance(e, dict) or set(e) != {"item", "unit", "quantity", "rate", "amount_cents", "ledger", "godowns"}
            or any(not isinstance(e[k], str) for k in ("item", "unit", "quantity", "rate", "ledger"))
            or type(e["amount_cents"]) is not int or not isinstance(e["godowns"], list)
            or any(not isinstance(g, dict) or set(g) != {"godown", "quantity", "amount_cents"}
                   or not isinstance(g["godown"], str) or not isinstance(g["quantity"], str)
                   or type(g["amount_cents"]) is not int for g in e["godowns"])
            for e in current["inventory"]):
        raise ValueError("Invalid inventory readback.")
    return current


def _lines(plan):
    return sorted(({"ledger": ln["ledger"], "amount_cents": _signed(ln)} for ln in plan["lines"]),
                  key=lambda e: (e["ledger"], e["amount_cents"]))


def _allocations(plan):
    """Every cost centre's share of the plan's lines, signed as Tally reports it."""
    return sorted(({"ledger": ln["ledger"], "category": a["category"], "centre": a["centre"],
                    "amount_cents": a["amount_cents"] if ln["side"] == "credit" else -a["amount_cents"]}
                   for ln in plan["lines"] for a in line_allocations(ln)),
                  key=lambda a: (a["ledger"], a["amount_cents"]))


def _bills(bills):
    return sorted(bills, key=lambda b: (b["ledger"], b["amount_cents"], b["type"], b["name"] or ""))


def _planned_bills(plan):
    """The bill references the plan approves, signed as Tally reports them."""
    return _bills([{"ledger": ln["ledger"], "name": bill.get("name"), "type": bill["type"],
                    "amount_cents": bill["amount_cents"] if ln["side"] == "credit" else -bill["amount_cents"]}
                   for ln in plan["lines"] for bill in ln.get("bills") or []])


def _inventory(entries):
    """Inventory entries in one comparable order, each with its godowns sorted."""
    return sorted(({**e, "godowns": sorted(e["godowns"], key=lambda g: (g["godown"], g["amount_cents"]))}
                   for e in entries), key=lambda e: (e["item"], e["amount_cents"], e["quantity"], e["ledger"]))


def _planned_inventory(plan):
    """The items the plan approves, signed as Tally reports them: an inward item is a debit."""
    sign = lambda entry: -1 if entry["side"] == "debit" else 1  # noqa: E731
    return _inventory([{"item": e["item"], "unit": e["unit"], "quantity": e["quantity"], "rate": e["rate"],
                    "amount_cents": sign(e) * e["amount_cents"], "ledger": e["ledger"],
                    "godowns": [{"godown": g["godown"], "quantity": g["quantity"], "amount_cents": sign(e) * g["amount_cents"]}
                                for g in e["godowns"]]} for e in plan.get("inventory") or []])


def _exact(plan, current):
    if (current["date"] != plan["header"]["date"].replace("-", "")
            or sorted(current["lines"], key=lambda e: (e["ledger"], e["amount_cents"])) != _lines(plan)
            or sorted(current["allocations"], key=lambda a: (a["ledger"], a["amount_cents"])) != _allocations(plan)
            or _bills(current["bills"]) != _planned_bills(plan)
            or _inventory(current["inventory"]) != _planned_inventory(plan)):
        raise ValueError("Tally readback differs from the approved amounts, ledgers, bill references or items.")


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
    series = (plan.get("identity") or {}).get("series", "invoice")
    try:
        issued = date.fromisoformat(f"{current['date'][:4]}-{current['date'][4:6]}-{current['date'][6:]}")
        same = number is not None and document_identity(current["party_ledger"], number, issued, series=series) == identity
    except ValueError:
        same = False
    if not same or current["family"] not in plan["duplicate"]["families"]:
        raise ValueError("Readback belongs to a different bill.")
    if outcome in ("saved", "duplicate"):
        _exact(plan, current)
        if outcome == "saved":
            _stated(plan, current)
            expected = plan.get("expected")
            if expected and current["guid"] != expected["guid"]:
                raise ValueError("Tally returned a different voucher identifier.")
            # An alteration keeps the existing voucher's own type; a new voucher uses the run's.
            if not expected and normalized(current["voucher_type"]) != normalized(plan["voucher_type"]["NAME"]):
                raise ValueError("Tally saved the bill under a different voucher type.")
    return {"master_id": current["master_id"], "guid": current["guid"], "date": current["date"],
            "invoice_number": number, "vendor": current["party_ledger"], "voucher_type": current["voucher_type"],
            "entries": _entries(current), "bills": current["bills"], "inventory": current["inventory"],
            "fingerprint": current["fingerprint"], **({"gst": current["gst"]} if "gst" in current else {})}


def _stated(plan, current):
    """A save writing GST details must read them back as written: the supplier's, and the registration Tally used."""
    planned = plan.get("gst")
    if not planned:
        return
    read = current.get("gst")
    party = planned["party"]
    wanted = {"party_gstin": party["gstin"], "registration_type": party["registration_type"], "state": party["state"],
              "country": party["country"], "place_of_supply": party["place_of_supply"],
              "company_gstin": planned["company_gstin"]}
    if read is None or any(read[key] != value for key, value in wanted.items()):
        raise ValueError("Tally's readback does not show the GST details Minkops wrote for this bill.")


def differences(plan, current):
    """How a voucher Tally holds for this bill differs from the approved plan, as clauses a person reads; none when it
    records the bill as planned: its date and voucher type, every ledger and amount, and, those being equal, its cost
    allocations and bill references.

    `current` is an observed voucher: a receipt's that observed_bill has accepted, or a stored one (mirror.observed).
    """
    theirs = Counter((line["ledger"], line["amount_cents"]) for line in current["lines"])
    ours = Counter((line["ledger"], _signed(line)) for line in plan["lines"])
    ledgers = {side: {ledger for ledger, _ in lines} for side, lines in (("theirs", theirs), ("ours", ours))}
    there, here = sorted(ledgers["theirs"] - ledgers["ours"]), sorted(ledgers["ours"] - ledgers["theirs"])
    party = plan["header"]["party_ledger"]

    def amounts(lines, ledger):
        return sorted(cents for name, cents in lines.elements() if name == ledger)

    clauses = []
    if current["date"] != plan["header"]["date"].replace("-", ""):
        clauses.append(f"is dated {current['date'][:4]}-{current['date'][4:6]}-{current['date'][6:]}")
    if normalized(current["voucher_type"]) != normalized(plan["voucher_type"]["NAME"]):
        clauses.append(f"is a {current['voucher_type']}, not a {plan['voucher_type']['NAME']}")
    if there and here:
        clauses.append(f"posts to {', '.join(there)} instead of {', '.join(here)}")
    elif there or here:
        clauses.append(f"also posts to {', '.join(there)}" if there else f"does not post to {', '.join(here)}")
    total = {side: sum(abs(cents) for cents in amounts(lines, party)) for side, lines in (("theirs", theirs),
                                                                                         ("ours", ours))}
    changed = sorted(ledger for ledger in (ledgers["theirs"] & ledgers["ours"]) - {party}
                     if amounts(theirs, ledger) != amounts(ours, ledger))
    if total["theirs"] != total["ours"]:
        clauses.append(f"comes to {rupees(total['theirs'])}, not {rupees(total['ours'])}"
                       + (f", with other amounts for {', '.join(changed)}" if changed else ""))
    elif changed:
        clauses.append(f"has other amounts for {', '.join(changed)}")
    if clauses:
        return clauses
    if sorted(current["allocations"], key=lambda a: (a["ledger"], a["amount_cents"])) != _allocations(plan):
        clauses.append("has other cost allocations")
    kept, planned = _bills(current.get("bills") or []), _planned_bills(plan)
    if kept != planned:
        named = lambda bills: ", ".join(f"{b['type']} {b['name']}" if b["name"] else b["type"] for b in bills)  # noqa: E731
        clauses.append(f"carries the bill reference {named(kept)} instead of {named(planned)}" if kept and planned
                       else f"carries the bill reference {named(kept)}" if kept
                       else f"carries no bill reference instead of {named(planned)}")
    return clauses


def correction_reason(plan, current):
    """How the voucher Tally already has for this bill differs from the approved plan, for the person reviewing it."""
    clauses = differences(plan, current)
    found = (f"Tally's voucher for {plan['duplicate']['number']} {'; '.join(clauses)}." if clauses
             else "Tally already has this bill with other amounts or ledgers.")
    return f"{found} Review it there; Minkops did not add a second voucher."


def observed_statement(plan, current):
    """A verified v5 statement receipt as the stored row observation."""
    current = _current(current)
    if current["tag"] != plan["remote_id"] or current["voucher_type"] != plan["voucher_type"]["NAME"]:
        raise ValueError("Native statement readback differs from the approved manifest.")
    _exact(plan, current)
    return {"guid": current["guid"], "master_id": current["master_id"], "fingerprint": current["fingerprint"],
            "date": current["date"], "voucher_type": current["voucher_type"], "tag": current["tag"],
            "entries": _entries(current), "allocations": current["allocations"], "bills": current["bills"]}


# ---------------------------------------------------------------------------
# Bill proposals: the session reads values from the bill and selects identities
# from the routed company's mirror; this binds them and enforces the rules every
# accounting voucher must satisfy before a plan exists.

# The families a document may be booked as. A purchase may already be a Journal, so a
# duplicate of an invoice is looked for among both.
KIND_FAMILIES = {"invoice": ("purchase", "journal"), "credit_note": ("debit_note",)}
BASE_FAMILY = {"purchase": "purchase", "journal": "journal", "debit note": "debit_note"}
PARTY_SIDE = {"purchase": "credit", "journal": "credit", "debit_note": "debit"}
LINE_ROLES = {"expense", "tax", "round_off", "freight", "other_charge", "discount", "tds", "retention", "deposit"}
# Held back from what the supplier is paid, on the supplier's side: TDS, and retention or contractual withholding.
DEDUCTIONS = {"tds", "retention"}
# Lines that carry the bill's taxable value, as opposed to its tax and adjustments.
TAXABLE_ROLES = {"expense", "freight", "other_charge"}
# A printed round-off never exceeds one rupee; anything more is not rounding.
ROUND_OFF_CAP_CENTS = 100
# Printed amounts are rounded to the rupee at most: a computed one may differ by that.
TOLERANCE_CENTS = 100


class HoldReason(ValueError):
    """A server-side hold with a stable code from the hold matrix (holds.py).

    `final` holds at once, whatever its code: no later reading could clear it.
    """

    def __init__(self, code, message, *, final=False):
        super().__init__(message)
        self.code, self.final = code, final


def rupees(cents):
    """An amount as a person reads it in Indian accounts: the last three digits, then pairs (12,50,000.00).

    Every reason, hold and label written for people uses it; amounts handed to
    a session or returned as data stay plain decimals.
    """
    whole, paise = divmod(abs(cents), 100)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    pairs = [head[max(0, end - 2):end] for end in range(len(head), 0, -2)][::-1]
    return f"{'-' if cents < 0 else ''}{','.join([*pairs, tail])}.{paise:02d}"


def _money(value, what, *, zero=False):
    """Exact positive paise from a bill amount, or zero where a bill may print none (`zero`); else a coded hold."""
    if type(value) not in (int, float):
        raise HoldReason("source_values_conflict", f"{what} must be a number printed on the bill.")
    cents = _cents(value)
    if cents is None or cents < (0 if zero else 1) or cents > 2**53 - 1:
        least = "zero or more" if zero else "a positive amount"
        raise HoldReason("source_values_conflict", f"{what} must be {least}, with at most two decimal places.")
    return cents


class Masters:
    """One company's pinned native masters, addressed by GUID only.

    `view` is a company in the mirror's view shape (mirror.company_view);
    `created` adds masters Minkops created since, verified by native readback.
    """

    def __init__(self, view, created=()):
        self.by_key, self.by_name = {}, {}
        for record in [*view["masters"]["records"], *created]:
            guid = text(record["data"].get("GUID"))
            if guid:
                self.by_key.setdefault((record["type"], guid), []).append(record["data"])
            self.by_name.setdefault((record["type"], self.name(record["data"]).casefold()), []).append(record["data"])
        types = [d for (kind, _), found in self.by_key.items() if kind == "VOUCHERTYPE" for d in found]
        self.bases = base_types(types)

    def name(self, data):
        return text(data.get("@_NAME")) or text(data.get("NAME"))

    def scalar(self, data, key):
        return text(data.get(key))

    def all(self, kind):
        """Every master of this type."""
        return [data for (found, _), records in self.by_key.items() if found == kind for data in records]

    def one(self, kind, guid, code, message):
        found = self.by_key.get((kind, guid)) if isinstance(guid, str) else None
        if not found or len(found) != 1:
            raise HoldReason(code, message)
        return found[0]

    def named(self, kind, name):
        """The one master of this type with this name, or None; stock items name their units."""
        found = self.by_name.get((kind, name.casefold()), [])
        return found[0] if len(found) == 1 else None

    def identity(self, data):
        return {key: text(data.get(key)) for key in ("GUID", "PARENT", "ALTERID")}

    def family(self, voucher_type):
        return BASE_FAMILY.get(str(self.bases.get(self.name(voucher_type).casefold()) or "").casefold())


def _tax_consistent(lines):
    """Hold tax lines that disagree with their own printed rate and base.

    `lines` are the bill's tax lines as dicts with "head" (cgst/sgst/igst/cess),
    "rate" (Decimal percent), "taxable_cents" and "amount_cents" (ints).
    """
    halves = {}
    for line in lines:
        expected = (line["rate"] * line["taxable_cents"] / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if abs(line["amount_cents"] - int(expected)) > TOLERANCE_CENTS:
            raise HoldReason("source_values_conflict",
                             f"A {line['head'].upper()} line does not match its printed rate and taxable value.")
        if line["head"] in ("cgst", "sgst"):
            halves.setdefault((line["rate"], line["taxable_cents"]), {}).setdefault(line["head"], []).append(
                line["amount_cents"])
    for pair in halves.values():
        if "cgst" in pair and "sgst" in pair and sorted(pair["cgst"]) != sorted(pair["sgst"]):
            raise HoldReason("source_values_conflict", "Central and state tax on the same rate and value must be equal.")


def _printed_totals(document, lines, raw, items_cents=0):
    """Tax-inclusive amounts: the bill's printed taxable and tax totals bind the lines that claim them.

    A bill whose amount column already includes GST can balance with no tax line
    at all, losing the input tax; its printed totals expose that. Items carry
    taxable value too.
    """
    for key, roles, what in (("taxable", TAXABLE_ROLES, "taxable value"), ("tax", {"tax"}, "tax")):
        printed = document.get(key)
        if printed is None:
            continue
        # An exempt or unregistered supply prints no tax at all, which binds the bill to no tax lines.
        cents = _money(printed, f"The bill's printed {what}", zero=key == "tax")
        claimed = (items_cents if key == "taxable" else 0) + sum(
            ln["amount_cents"] for ln, item in zip(lines, raw, strict=True) if item["role"] in roles)
        if abs(claimed - cents) > TOLERANCE_CENTS:
            raise HoldReason("source_values_conflict", (
                f"The lines claim {rupees(claimed)} of {what}, but the bill prints {rupees(cents)}. "
                "Each expense line must carry its taxable value, and each tax its own line."))


def _split_key(line, item):
    """What sets a ledger's lines apart in Tally: side, GST rate and supply, and a tax line's head and rate."""
    tax = item.get("tax") or {}
    return line["ledger"], line["side"], item.get("gst_rate"), item.get("supply"), tax.get("head"), tax.get("rate")


def _repeated(lines, raw):
    """A ledger may carry several lines: one per GST rate it is taxed at, or per cost centre the bill allocates it to.

    Lines nothing sets apart are one amount split for no reason Tally keeps, so the session adds them up.
    """
    groups = {}
    for ln, item in zip(lines, raw, strict=True):
        groups.setdefault(_split_key(ln, item), []).append(ln)
    for key, group in groups.items():
        centres = [ln["allocation"]["centre"] for ln in group if ln["allocation"]]
        if len(group) > 1 and (len(centres) < len(group) or len(set(centres)) < len(centres)):
            raise HoldReason("classification_uncertain", (
                f"{key[0]} is on more than one line: give it one line with the sum of the bill's amounts it carries, "
                "or one line for each cost centre or GST rate the bill splits it by."))


def _merged(lines, raw):
    """The voucher's own lines: a ledger's lines that differ only by cost centre are one line carrying each share."""
    merged, at = [], {}
    for ln, item in zip(lines, raw, strict=True):
        key = _split_key(ln, item)
        if ln["allocation"] and key in at:
            carrier = merged[at[key]]
            if not carrier.get("allocations"):
                carrier["allocations"] = [{**carrier["allocation"], "amount_cents": carrier["amount_cents"]}]
                carrier["allocation"] = None
            carrier["allocations"].append({**ln["allocation"], "amount_cents": ln["amount_cents"]})
            carrier["amount_cents"] += ln["amount_cents"]
        else:
            at[key] = len(merged)
            merged.append(dict(ln))
    return merged


def _split(document, lines):
    """A cost split the bill prints, between two or more sites or projects, is carried at its printed shares.

    Booked to the supplier's usual ledger, which may keep no cost centres, a split was dropped unseen, and with
    precedent behind the booking it was written so. Centres are matched by share, not by name: the session chose each
    by reference, and a project's printed name need not be Tally's.
    """
    parts = document.get("cost_split") or []
    if not isinstance(parts, list) or len(parts) < 2:
        return
    if any(not isinstance(part, dict) or not isinstance(part.get("name"), str) or not part["name"].strip()
           or (part.get("amount") is None) == (part.get("percent") is None) for part in parts):
        raise HoldReason("source_values_conflict", "Each part of a printed split needs its name, and its amount or "
                                                   "its percentage as the bill prints it.")
    percents = all(part.get("percent") is not None for part in parts)

    def listed(labels):
        return " and ".join(labels) if len(labels) < 3 else f"{', '.join(labels[:-1])} and {labels[-1]}"
    printed = listed([f"{part['name'].strip()} ({part['percent']:g}%)" if percents
                      else f"{part['name'].strip()} ({rupees(_money(part['amount'], 'A printed share'))})"
                      for part in parts])
    allocated = {}
    for line in lines:
        if line["allocation"]:
            centre = line["allocation"]["centre"]
            allocated[centre] = allocated.get(centre, 0) + line["amount_cents"]
    if not allocated:
        raise HoldReason("classification_uncertain", (
            f"The bill splits its cost between {printed}, but the voucher allocates none of it. Carry each part on its "
            "cost centre, on a ledger that keeps them; if the company has no such ledger for this cost, propose "
            "classification_uncertain and name the split."))
    total = sum(allocated.values())
    if percents:
        wanted = sorted(Decimal(str(part["percent"])) for part in parts)
        carried = sorted(Decimal(cents) * 100 / total for cents in allocated.values())
        matches = len(carried) == len(wanted) and all(abs(c - w) <= Decimal("0.5") for c, w in zip(carried, wanted, strict=True))
        shown = listed([f"{share.quantize(Decimal(1)):f}%" for share in sorted(carried, reverse=True)])
    else:
        wanted = sorted(_money(part["amount"], "A printed share") for part in parts)
        carried = sorted(allocated.values())
        matches = len(carried) == len(wanted) and all(abs(c - w) <= TOLERANCE_CENTS for c, w in zip(carried, wanted, strict=True))
        shown = listed([rupees(cents) for cents in sorted(carried, reverse=True)])
    if not matches:
        raise HoldReason("classification_uncertain", (
            f"The bill splits its cost between {printed}, but the voucher allocates {shown}. Carry each part on its "
            "cost centre at the share the bill prints."))


def _adjustments(document, raw, lines, retained, company):
    """What the bill prints as held back, refundable or adjusted is carried by the voucher; returns notes for a person.

    Retention or contractual withholding is a retention line on the supplier's side, and a refundable deposit a
    deposit line, never an expense: a bill printing one the voucher does not carry is refused, so the session books
    it or names its uncertainty. An advance already paid is matched against the bill in Tally; the bill is booked at
    its full value, and the note keeps standing approval from writing it unseen.
    """
    printed = document.get("adjustments") or []
    deposits = [ln["amount_cents"] for ln, item in zip(lines, raw, strict=True) if item["role"] == "deposit"]
    notes = []
    for adjustment in printed:
        kind = adjustment.get("kind") if isinstance(adjustment, dict) else None
        if kind not in ("advance", "retention", "withholding", "deposit"):
            raise HoldReason("source_values_conflict", "Each printed adjustment is an advance, retention, withholding "
                                                       "or deposit.")
        cents = _money(adjustment.get("amount"), f"The printed {kind}")
        if kind == "advance":
            notes.append(f"The bill adjusts an advance of {rupees(cents)} already paid. Minkops books the bill at its "
                         "full value; match it against that advance in Tally.")
        elif kind in ("retention", "withholding") and cents not in retained:
            raise HoldReason("classification_uncertain", (
                f"The bill holds back {rupees(cents)} as {kind} from what the supplier is paid. Carry it as a retention "
                f"line on the supplier's side, to the ledger {company['name']} keeps it in; if it keeps none, propose "
                "classification_uncertain."))
        elif kind == "deposit" and cents not in deposits:
            raise HoldReason("classification_uncertain", (
                f"The bill charges a refundable deposit of {rupees(cents)}, which is not an expense. Carry it as a "
                f"deposit line to the ledger {company['name']} keeps deposits in; if it keeps none, propose "
                "classification_uncertain."))
    return notes


def _decimal(value, what, places, precision=None):
    """A positive printed number with at most `places` decimals, exactly; `precision` says why more cannot be kept."""
    if type(value) not in (int, float):
        raise HoldReason("source_values_conflict", f"{what} must be a number printed on the bill.")
    number = Decimal(str(value)).normalize()
    if not number.is_finite() or number <= 0:
        raise HoldReason("source_values_conflict", f"{what} must be a positive number printed on the bill.")
    if -min(number.as_tuple().exponent, 0) > places:
        raise HoldReason("source_values_conflict", precision or f"{what} has more than {places} decimal places.")
    return number


def _figure(number):
    """A quantity or rate as plain text, without trailing zeros: Tally's 1.250 MT reads back as 1.25."""
    return format(number.normalize(), "f")


@dataclass(frozen=True)
class Stock:
    """A bill's items: each to its godowns and purchase ledger, and the ledger lines Tally books for them."""

    entries: list
    ledgers: dict  # purchase ledger -> paise, in the items' order
    identities: dict  # purchase ledger -> its identity
    items: dict  # stock item -> {GUID, BASEUNITS}, as the companion rechecks it
    godowns: dict  # godown -> {GUID}

    @property
    def cents(self):
        return sum(self.ledgers.values())


def _stock(masters, items, party_name):
    """Bind a bill's items to stock items, their godowns and the ledgers that carry their value in Tally."""
    entries, ledgers, identities, known, godowns = [], {}, {}, {}, {}
    if not isinstance(items, list) or len(items) > 40:
        raise HoldReason("unsupported_structure", "A bill carries at most 40 item lines.")
    for raw_item in items:
        if not isinstance(raw_item, dict) or not isinstance(raw_item.get("evidence"), str) or not raw_item["evidence"].strip():
            raise HoldReason("source_values_conflict", "Each item needs its stock item, figures and bill evidence.")
        stock = masters.one("STOCKITEM", raw_item.get("item_guid"), "classification_uncertain",
                            "Each item must select one stock item of the routed company.")
        name, unit_name = masters.name(stock), masters.scalar(stock, "BASEUNITS")
        if any(masters.scalar(stock, flag).casefold() == "yes" for flag in ("ISBATCHWISEON", "ISPERISHABLEON",
                                                                            "HASMFGDATE")):
            raise HoldReason("unsupported_structure", f"{name} tracks batches in Tally, so its purchase names the batch "
                                                      "there. Enter this bill in Tally.")
        unit = masters.named("UNIT", unit_name)
        if unit is None or masters.scalar(unit, "ISSIMPLEUNIT").casefold() == "no":
            raise HoldReason("unsupported_structure", f"{name} is counted in a compound unit ({unit_name}). Enter this "
                                                      "bill in Tally.")
        places = int(masters.scalar(unit, "DECIMALPLACES") or 0)
        counted = f"{name} is counted in {unit_name} to {places} decimal places in Tally."
        quantity = _decimal(raw_item.get("quantity"), f"{name}'s quantity", places, counted)
        rate = _decimal(raw_item.get("rate"), f"{name}'s rate", 4)
        amount = _money(raw_item.get("amount"), f"{name}'s amount")
        priced = int((quantity * rate * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if abs(priced - amount) > TOLERANCE_CENTS:
            raise HoldReason("source_values_conflict", f"{name}: {_figure(quantity)} at {_figure(rate)} comes to "
                                                       f"{rupees(priced)}, but the bill prints {rupees(amount)}.")
        ledger = masters.one("LEDGER", raw_item.get("ledger_guid"), "classification_uncertain",
                             "Each item must select one purchase ledger of the routed company.")
        ledger_name = masters.name(ledger)
        if ledger_name == party_name:
            raise HoldReason("classification_uncertain", "An item's value goes to a purchase ledger, not the supplier.")
        if masters.scalar(ledger, "AFFECTSSTOCK").casefold() != "yes":
            raise HoldReason("classification_uncertain", f"{ledger_name} must have inventory values affected in Tally "
                                                         "to carry stock items.")
        split, taken, taken_quantity = [], 0, Decimal(0)
        for place in raw_item.get("godowns") if isinstance(raw_item.get("godowns"), list) else []:
            godown = masters.one("GODOWN", (place or {}).get("godown_guid"), "classification_uncertain",
                                 "Each godown must be one godown of the routed company.")
            godown_name = masters.name(godown)
            moved = _decimal(place.get("quantity"), f"{name}'s quantity in {godown_name}", places, counted)
            cents = _money(place.get("amount"), f"{name}'s amount in {godown_name}")
            if any(entry["godown"] == godown_name for entry in split):
                raise HoldReason("classification_uncertain", f"{name} names {godown_name} twice.")
            split.append({"godown": godown_name, "quantity": _figure(moved), "amount_cents": cents})
            godowns[godown_name] = {"GUID": masters.scalar(godown, "GUID")}
            taken, taken_quantity = taken + cents, taken_quantity + moved
        if not 1 <= len(split) <= 10 or taken != amount or taken_quantity != quantity:
            raise HoldReason("classification_uncertain", f"{name}'s godowns must take its {_figure(quantity)} "
                                                         f"{unit_name} and {rupees(amount)} between them.")
        entries.append({"item": name, "unit": unit_name, "quantity": _figure(quantity), "rate": _figure(rate),
                        "side": "debit", "amount_cents": amount, "ledger": ledger_name, "godowns": split})
        ledgers[ledger_name] = ledgers.get(ledger_name, 0) + amount
        identities[ledger_name] = masters.identity(ledger)
        known[name] = {"GUID": masters.scalar(stock, "GUID"), "BASEUNITS": unit_name}
    return Stock(entries, ledgers, identities, known, godowns)


class Bill:
    """A proposal bound to the company's identities; the single source of its plan."""

    def __init__(self, company, record, family, voucher_type, party, party_identity, lines, identities, *,
                 billwise=False, stock=None, expense=(), returns=None, notes=()):
        document = record["document"]
        self.company, self.family, self.voucher_type, self.party = company, family, voucher_type, party
        self.kind, self.number, self.date = document["kind"], document["number"], document["date"]
        self.total_cents = _money(document["total"], "The bill total")
        self.lines, self.stock, self.expense = lines, stock, sorted(expense)
        # What Tally's GST returns need on the voucher (`_gst`), and the notes a person reviews before approving.
        self.returns, self.notes = returns, list(notes)
        self.identities = {party: party_identity, **identities} if party_identity else dict(identities)
        # A supplier kept bill by bill is owed a New Ref named by the invoice.
        self.billwise = billwise
        self.series = "credit_note" if self.kind == "credit_note" else "invoice"
        self.identity = document_identity(party, self.number, date.fromisoformat(self.date), series=self.series)

    @property
    def destination_key(self):
        return f"bill:{self.company['guid']}"

    @property
    def booking(self):
        """How the bill is booked, as confirmation by use compares it: voucher type, expense ledgers, item-wise."""
        return {"voucher_type": self.voucher_type, "ledgers": self.expense, "items": bool(self.stock)}

    def native_plan(self, remote_id, *, number_fields=("REFERENCE",), note=None):
        """The approved voucher; `note` adds what the company's practice records in the narration."""
        label = "credit note" if self.kind == "credit_note" else "bill"
        lines = [{**self.lines[0], "bills": [{"name": self.number, "type": "New Ref",
                                              "amount_cents": self.lines[0]["amount_cents"]}]},
                 *self.lines[1:]] if self.billwise else self.lines
        return {
            "format_version": plan_format(lines), "family": self.family, "operation": "append",
            "company": self.company["name"], "company_guid": self.company["guid"],
            "port": self.company.get("tally_port") or 9000, "remote_id": remote_id, "voucher_type": self.voucher_type,
            "header": {"date": self.date, "reference": self.number, "party_ledger": self.party,
                       "narration": f"Minkops reviewed {label} {self.number}" + (f"; {note}" if note else ""),
                       "tag": None},
            "lines": lines,
            "references": {"company_guid": self.company["guid"], "ledgers": self.identities,
                           **({"stock_items": self.stock.items, "godowns": self.stock.godowns} if self.stock else {})},
            **({"inventory": self.stock.entries} if self.stock else {}),
            **({"gst": self.returns} if self.returns else {}),
            "duplicate": {"strategy": "document", "families": list(KIND_FAMILIES[self.kind]) if self.kind == "invoice"
                          else ["debit_note"], "party_ledger": self.party, "number": self.number,
                          "number_fields": list(number_fields), "window": invoice_window(date.fromisoformat(self.date))},
            "fence": "retry_after_read", "expected": None,
            "identity": {"version": 2, "series": self.series, "rule": "in_invoice_year", "hash": self.identity},
        }

    def preview(self):
        """What the reviewer sees will be entered, in native names."""
        return {"company": self.company["name"], "voucher_type": self.voucher_type["NAME"], "family": self.family,
                "date": self.date, "number": self.number, "party": self.party, "total": self.total_cents / 100,
                "lines": [{"ledger": ln["ledger"], "side": ln["side"], "amount": ln["amount_cents"] / 100}
                          for ln in self.lines],
                **({"items": [{"item": entry["item"], "quantity": entry["quantity"], "unit": entry["unit"],
                               "rate": entry["rate"], "amount": entry["amount_cents"] / 100, "ledger": entry["ledger"],
                               "godowns": [place["godown"] for place in entry["godowns"]]}
                              for entry in self.stock.entries]} if self.stock else {})}


def _document(record):
    document, voucher = record.get("document"), record.get("voucher")
    if not isinstance(document, dict) or not isinstance(voucher, dict):
        raise HoldReason("required_value_missing", "The bill needs its document and a proposed voucher.")
    missing = [key for key in ("kind", "number", "date", "total", "supplier_name", "origin")
               if document.get(key) is None or (isinstance(document[key], str) and not document[key].strip())]
    if missing:
        raise HoldReason("required_value_missing", f"The bill's {', '.join(missing)} must be read from it.")
    if not isinstance(document["number"], str) or len(document["number"]) > 100:
        raise HoldReason("required_value_missing", "The bill's document number is missing.")
    try:
        date.fromisoformat(document["date"])
    except (TypeError, ValueError):
        raise HoldReason("required_value_missing", "The bill's date must be a calendar date.") from None
    if document["origin"] != "domestic":
        raise HoldReason("identity_rule_unknown",
                         "Only domestic supplier documents have a known invoice numbering year. Enter this bill in Tally.")
    if document.get("kind") not in KIND_FAMILIES or voucher.get("family") not in KIND_FAMILIES[document["kind"]]:
        raise HoldReason("classification_uncertain", "The voucher family must match the document: invoices are "
                                                     "Purchase or Journal, supplier credit notes are Debit Notes.")
    _money(document.get("total"), "The bill total")
    return document, voucher


def check(record, view, company, *, created=(), until=None, assume_new_supplier=False):
    """Bind a bill proposal to its company's pinned masters and enforce the voucher rules.

    `company` is the destination (name, guid, books_from, tally_port); `until`
    is the last day before a year-split sibling's books begin. Returns a Bill,
    or raises a coded HoldReason. The session chose every identity; this only
    proves each one exists, is active and distinct, and agrees with the bill's
    own printed values.
    """
    document, voucher = _document(record)
    masters = Masters(view, created)
    # How the company keeps its books, as its books or its client settled it (practice.py): absent when unsettled.
    practices = {key: value for key, value in (view.get("practices") or {}).items() if value}
    books_from = company["books_from"].isoformat()
    if document["date"] < books_from:
        raise HoldReason("date_before_books", f"Bill date {document['date']} is before {company['name']}'s books begin on "
                                              f"{books_from}; Tally cannot record it without a change to the company's books.")
    if until and document["date"] > until:
        raise HoldReason("date_outside_company_period", f"Bill date {document['date']} is after {company['name']}'s books "
                                                        f"end on {until}; it belongs to the next year's company.")
    family = voucher["family"]
    voucher_type = masters.one("VOUCHERTYPE", voucher.get("voucher_type_guid"), "voucher_type_unresolved",
                               "Select one active voucher type of the routed company.")
    if masters.family(voucher_type) != family or masters.scalar(voucher_type, "ISACTIVE").casefold() == "no":
        raise HoldReason("voucher_type_unresolved", f"The voucher type must be an active {family.replace('_', ' ')} type.")
    party = voucher.get("party") or {}
    if party.get("ledger_guid") is None:
        if party.get("new_supplier") is not True:
            raise HoldReason("supplier_unresolved", "Supplier match is unresolved; a new supplier has not been established.")
        if not assume_new_supplier:
            raise HoldReason("supplier_missing", f"Supplier '{document.get('supplier_name')}' has no ledger in "
                                                 f"{company['name']}. Create it, then this bill can be saved.")
        party_name, party_identity, supplier = document.get("supplier_name"), None, None
    else:
        ledger = masters.one("LEDGER", party["ledger_guid"], "supplier_unresolved", "The supplier must be one ledger.")
        party_name, party_identity, supplier = masters.name(ledger), masters.identity(ledger), ledger
        printed, held = (document.get("supplier_gstin") or "").strip().upper(), gst.supplier_gstins(ledger)
        if printed and held and printed not in held:
            raise HoldReason("supplier_unresolved", f"The bill's supplier GSTIN {printed} is not {party_name}'s in Tally. "
                                                    "Choose the supplier ledger with this GSTIN, or propose supplier_unresolved.")
    billwise = party_identity is not None and masters.scalar(ledger, "ISBILLWISEON").casefold() == "yes"
    if billwise and document["kind"] == "credit_note":
        raise HoldReason("unsupported_structure", f"{party_name} keeps bill-by-bill balances, so its debit note must "
                                                  "name the bill it adjusts. Enter it in Tally.")
    if not isinstance(party.get("evidence"), str) or not party["evidence"].strip():
        raise HoldReason("supplier_unresolved", "The supplier selection needs evidence.")
    stock = None
    if voucher.get("items"):
        if family != "purchase":
            raise HoldReason("unsupported_structure", "Stock items are entered on a Purchase invoice. Goods returned on "
                                                      "a credit note, or items on a Journal, are entered in Tally.")
        stock = _stock(masters, voucher["items"], party_name)
    raw = voucher.get("lines")
    if not isinstance(raw, list) or not (0 if stock else 1) <= len(raw) <= 39 - (len(stock.ledgers) if stock else 0):
        raise HoldReason("unsupported_structure", "A bill voucher carries 1–39 lines besides the supplier.")
    lines, identities, taxes, tds, round_offs, retained = [], dict(stock.identities) if stock else {}, [], [], 0, []
    # Every line is checked, and every faulty one named at once: refused one at a time, a session corrects one per
    # attempt and is held before it sees the rest.
    faults = []
    for item in raw:
        try:
            if (not isinstance(item, dict) or item.get("role") not in LINE_ROLES or item.get("side") not in ("debit", "credit")
                    or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()):
                raise HoldReason("source_values_conflict", "Each voucher line needs a known role, a side and bill evidence.")
            cents = _money(item.get("amount"), "Each line amount")
            ledger = masters.one("LEDGER", item.get("ledger_guid"), "classification_uncertain",
                                 "Each line must select one ledger of the routed company.")
            name = masters.name(ledger)
            if name == party_name:
                raise HoldReason("classification_uncertain", f"{name} is the supplier's ledger: Minkops writes its line "
                                                             "from the bill's total.")
            if stock and name in stock.identities:
                raise HoldReason("classification_uncertain", f"{name} is on more than one line: give it one line with the "
                                                             "sum of the bill's amounts it carries.")
            if item["role"] in TAXABLE_ROLES and gst.is_duty(ledger):
                # Tally's returns read a duty ledger as tax: a taxable value posted to one is claimed as input tax.
                what = item["role"].replace("_", " ")
                raise HoldReason("classification_uncertain", f"{name} is a GST duty ledger: it carries the bill's tax, "
                                                             f"never its {what}. Book the {what} to the ledger the "
                                                             "company uses for it.")
            identities.setdefault(name, masters.identity(ledger))
            allocation = None
            if item.get("cost_centre_guid") or item.get("cost_category_guid"):
                centre = masters.one("COSTCENTRE", item.get("cost_centre_guid"), "classification_uncertain",
                                     "Select one cost centre.")
                category = masters.one("COSTCATEGORY", item.get("cost_category_guid"), "classification_uncertain",
                                       "Select one cost category.")
                if masters.scalar(centre, "CATEGORY").casefold() != masters.name(category).casefold():
                    raise HoldReason("classification_uncertain", "The cost centre does not belong to the selected cost category.")
                if masters.scalar(ledger, "ISCOSTCENTRESON").casefold() != "yes":
                    raise HoldReason("classification_uncertain", f"{name} must enable cost centres in Tally before allocating it.")
                allocation = {"category": masters.name(category), "category_guid": masters.scalar(category, "GUID"),
                              "centre": masters.name(centre), "centre_guid": masters.scalar(centre, "GUID")}
            if item["role"] == "tds":
                rule = item.get("tds")
                if (item["side"] != PARTY_SIDE[family] or not isinstance(rule, dict) or not isinstance(rule.get("section"), str)
                        or type(rule.get("rate")) not in (int, float) or not 0 < rule["rate"] <= 30):
                    raise HoldReason("classification_uncertain",
                                     "A TDS deduction needs its section and rate, and reduces what the supplier is owed.")
                tds.append((rule, cents))
            if item["role"] == "retention":
                if item["side"] != PARTY_SIDE[family]:
                    raise HoldReason("classification_uncertain", "A retention line holds back part of what the supplier is "
                                                                 "owed, so it is on the supplier's side.")
                retained.append(cents)
            if item["role"] == "round_off":
                round_offs += 1
                if cents > ROUND_OFF_CAP_CENTS:
                    raise HoldReason("source_values_conflict", "A round-off above one rupee is not a rounding difference.")
            if item["role"] == "tax":
                tax = item.get("tax")
                if (not isinstance(tax, dict) or tax.get("head") not in ("cgst", "sgst", "igst", "cess")
                        or type(tax.get("rate")) not in (int, float) or not 0 < tax["rate"] <= 100):
                    raise HoldReason("source_values_conflict", "Each tax line needs its tax head and printed rate.")
                taxes.append({"head": tax["head"], "rate": Decimal(str(tax["rate"])), "amount_cents": cents,
                              "taxable_cents": _money(tax.get("taxable"), "The taxable value")})
                problem = gst.tax_ledger_problem(ledger, tax["head"], taxes[-1]["rate"])
                if problem:
                    raise HoldReason("classification_uncertain", problem)
                # A company whose purchases post GST to its duty ledgers, which Tally's returns read, uses one where
                # the books have it for this head and rate.
                duty = None if gst.is_duty(ledger) or practices.get("gst_ledgers", {}).get("use") != "gst_duty" else \
                    gst.duty_ledger(masters.all("LEDGER"), tax["head"], taxes[-1]["rate"])
                if duty:
                    raise HoldReason("classification_uncertain", (
                        f"{company['name']} posts GST to the ledgers Tally sets up as GST duties: use {duty} for "
                        f"{gst.HEAD_NAMES[tax['head']]} at {taxes[-1]['rate'].normalize():f}%."))
            if item["role"] == "discount" and practices.get("discounts", {}).get("booked") == "net":
                raise HoldReason("classification_uncertain", f"{company['name']} books a printed discount net: book each "
                                                             "line at its discounted value, with no discount line.")
            lines.append(_line(name, item["side"], cents, allocation))
        except HoldReason as fault:
            faults.append(fault)
    if faults:
        raise HoldReason(faults[0].code, " ".join(dict.fromkeys(str(f) for f in faults)),
                         final=any(f.final for f in faults))
    items_cents = stock.cents if stock else 0
    if tds:
        # Deducted on the contract value, the expense lines and items, never on GST.
        base = items_cents + sum(ln["amount_cents"] for ln, item in zip(lines, raw, strict=True)
                                 if item["role"] == "expense")
        for rule, cents in tds:
            expected = (Decimal(str(rule["rate"])) * base / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            if abs(cents - int(expected)) > TOLERANCE_CENTS:
                raise HoldReason("source_values_conflict",
                                 f"TDS does not match section {rule['section']} at {rule['rate']}% of the bill's value.")
    if round_offs > 1:
        raise HoldReason("source_values_conflict", "A bill has at most one round-off line.")
    _repeated(lines, raw)
    _split(document, lines)
    advances = _adjustments(document, raw, lines, retained, company)
    _tax_consistent(taxes)
    _printed_totals(document, lines, raw, items_cents)
    # The supplier's line is computed from the total, so the other lines must reach it exactly: what they
    # charge, less what they take off on the supplier's side. TDS only reduces what the supplier is owed.
    total, side = _money(document["total"], "The bill total"), PARTY_SIDE[family]
    reached = items_cents + sum(ln["amount_cents"] if ln["side"] != side else -ln["amount_cents"]
                                for ln, item in zip(lines, raw, strict=True) if item["role"] not in DEDUCTIONS)
    if reached != total:
        raise HoldReason("source_values_conflict", (
            f"The lines come to {rupees(reached)}, but the bill's printed total is {rupees(total)}. A round-off "
            "the bill prints, of at most one rupee, is its own line; any other difference means the bill's own "
            "figures conflict."))
    returns, notes = _gst(view, masters, company, document, family, raw, lines, taxes, supplier, party_name, stock)
    notes += advances
    # Tally books the items' value on their purchase ledgers, one line each, ahead of the bill's own lines.
    native = [_line(party_name, side, total - sum(cents for _, cents in tds) - sum(retained)),
              *(_line(ledger, "debit", cents) for ledger, cents in (stock.ledgers.items() if stock else ())),
              *_merged(lines, raw)]
    expense = {*(stock.ledgers if stock else ()),
               *(ln["ledger"] for ln, item in zip(lines, raw, strict=True) if item["role"] in TAXABLE_ROLES)}
    voucher_type_ref = {"NAME": masters.name(voucher_type), "GUID": masters.scalar(voucher_type, "GUID")}
    return Bill(company, record, family, voucher_type_ref, party_name, party_identity, native, identities,
                billwise=billwise, stock=stock, expense=expense, returns=returns, notes=notes)


def _gst(view, masters, company, document, family, raw, lines, taxes, ledger, party_name, stock):
    """What the voucher carries for Tally's GST returns, and the notes a person reviews, as (returns, notes).

    Only a company with GST switched on files returns. Its purchase states the supplier's registration and the
    place of supply, and each taxable line its rates, as TallyPrime needs to include it (gst.py); a debit note
    states the supplier's. Raises a HoldReason for a buyer, place or rate the bill does not settle. Lines gain
    their `gst` details in place.
    """
    registrations = gst.registrations(view)
    buyer = (document.get("buyer_gstin") or "").strip().upper()
    registration = None
    # Input tax is claimed only by a registered buyer, on a bill that names its GSTIN. A company with GST off in Tally
    # keeps its tax ledgers as plain bookkeeping, so only one with GST on is held to that.
    if taxes and not registrations and masters.scalar(view["identity"], "ISGSTON").casefold() == "yes":
        raise HoldReason("classification_uncertain", (
            f"{company['name']} has GST switched on in Tally but no GSTIN there, so it cannot claim this bill's input "
            "tax. Add the company's GSTIN in Tally, or decide whether the tax is part of the cost."), final=True)
    if registrations:
        if buyer:
            registration = next((r for r in registrations if r["gstin"] == buyer), None)
            if registration is None:
                raise HoldReason("company_unresolved", f"The bill is addressed to GSTIN {buyer}, which is not one of "
                                                       f"{company['name']}'s GST registrations in Tally.")
        elif len(registrations) == 1 and taxes:
            raise HoldReason("classification_uncertain", (
                f"{company['name']} can claim input tax only on a bill that prints its GSTIN as the buyer's. Give "
                "buyer_gstin as the bill prints it. If it prints none, propose classification_uncertain: whether the "
                "tax is claimed or is part of the cost is a person's call."))
        elif len(registrations) == 1:
            registration = registrations[0]
        else:
            raise HoldReason("company_unresolved", f"{company['name']} has {len(registrations)} GST registrations in "
                                                   "Tally: give the buyer GSTIN the bill is addressed to.")
    place, problem = gst.place_of_supply(document, registration, masters.scalar(view["identity"], "STATENAME"))
    if problem:
        raise HoldReason("source_values_conflict", problem)
    on = document["date"].replace("-", "")
    registered = gst.supplier(ledger, on) if ledger is not None else None
    printed = (document.get("supplier_gstin") or "").strip().upper()
    notes = [note for note in [gst.heads_note(taxes, printed or (registered or {}).get("gstin"), place)] if note]
    if registration is None or family not in ("purchase", "debit_note") or ledger is None:
        return None, notes
    if registered is None:
        if taxes:
            notes.append(f"Tally's GST returns cannot claim this bill's tax: {party_name} has no GSTIN in Tally. Add the "
                         "supplier's GSTIN to its ledger there.")
        return None, notes
    returns = {"party": {**registered, "place_of_supply": gst.tally_state(place, registration["state"],
                                                                            registered["state"])},
               "company_gstin": registration["gstin"],
               # Tally attaches a company's only registration itself; of several, the voucher names its own.
               "registration": ({"name": registration["name"], "gstin": registration["gstin"]}
                                if len(registrations) > 1 and registration["name"] else None)}
    if family != "purchase" or stock or not taxes:
        return returns, notes
    taxable = [(index, line["amount_cents"], raw[index].get("gst_rate")) for index, line in enumerate(lines)
               if raw[index]["role"] in TAXABLE_ROLES]
    try:
        rates = gst.line_rates(taxable, taxes)
    except ValueError as error:
        raise HoldReason("source_values_conflict", str(error)) from None
    cesses = {tax["rate"] for tax in taxes if tax["head"] == "cess"}
    cess = next(iter(cesses)) if len(cesses) == 1 and len(set(rates.values()) - {Decimal(0)}) == 1 else Decimal(0)
    for index, rate in rates.items():
        if not rate:
            continue
        supply = gst.SUPPLIES.get(raw[index].get("supply")) or masters.scalar(
            masters.one("LEDGER", raw[index]["ledger_guid"], "classification_uncertain", "Select one ledger."),
            "GSTTYPEOFSUPPLY").title() or None
        if supply not in ("Goods", "Services"):
            raise HoldReason("classification_uncertain", "Say whether each taxed line supplies goods or services.")
        lines[index]["gst"] = gst.line_details(rate, supply, cess)
    return returns, notes
