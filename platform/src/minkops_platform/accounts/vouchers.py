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


# ---------------------------------------------------------------------------
# Bill proposals (bill-entry 0.14+): the AI selects discovered identities and
# reads values from the bill; this module binds them and enforces the rules
# every accounting voucher must satisfy before a plan exists.

KIND_FAMILIES = {"invoice": ("purchase", "journal"), "credit_note": ("debit_note",)}
BASE_FAMILY = {"purchase": "purchase", "journal": "journal", "debit note": "debit_note"}
PARTY_SIDE = {"purchase": "credit", "journal": "credit", "debit_note": "debit"}
LINE_ROLES = {"expense", "tax", "round_off", "freight", "other_charge", "discount", "tds"}
# A printed round-off never exceeds one rupee; a posting profile may narrow it.
ROUND_OFF_CAP_CENTS = 100


def _hold(code, message):
    from .bills import HoldReason

    return HoldReason(code, message)


def _money(value, what):
    """Exact positive paise from a bill amount, or a coded hold."""
    if type(value) not in (int, float):
        raise _hold("source_values_conflict", f"{what} must be a number printed on the bill.")
    cents = _cents(value)
    if cents is None or cents <= 0 or cents > 2**53 - 1:
        raise _hold("source_values_conflict", f"{what} must be a positive amount with at most two decimal places.")
    return cents


class Masters:
    """One discovered company's native masters, addressed by GUID only."""

    def __init__(self, company, created=()):
        from .client_context import master_lookup, text

        self._text = text
        self.by_key = {}
        for record in [*master_lookup(company)["records"], *created]:
            guid = text(record["data"].get("GUID"))
            if guid:
                self.by_key.setdefault((record["type"], guid), []).append(record["data"])
        types = [d for (kind, _), found in self.by_key.items() if kind == "VOUCHERTYPE" for d in found]
        from .voucher_types import base_types

        self.bases = base_types(types)

    def name(self, data):
        return (self._text(data.get("@_NAME")) or self._text(data.get("NAME")) or "").strip()

    def scalar(self, data, key):
        return (self._text(data.get(key)) or "").strip()

    def one(self, kind, guid, code, message):
        found = self.by_key.get((kind, guid)) if isinstance(guid, str) else None
        if not found or len(found) != 1:
            raise _hold(code, message)
        return found[0]

    def identity(self, data):
        return {key: self._text(data.get(key)) for key in ("GUID", "PARENT", "ALTERID")}

    def family(self, voucher_type):
        return BASE_FAMILY.get(str(self.bases.get(self.name(voucher_type).casefold()) or "").casefold())


def _company(config, target):
    """The pinned discovery record of the company a bill was routed to."""
    guid = target["references"]["company_guid"]
    for source in config.get("source_catalog_snapshot", {}).get("sources", []):
        for company in (source.get("snapshot") or {}).get("companies", []):
            if company.get("company_guid") == guid:
                created = [m for m in config.get("created_masters", []) if m.get("company_guid") == guid]
                return Masters(company, created)
    raise _hold("company_unresolved", "The routed company is missing from the pinned Source Discovery.")


def _tax_consistent(lines):
    """Hold tax lines that disagree with their own printed rate and base.

    `lines` are the bill's tax lines as dicts with "head" (cgst/sgst/igst/cess),
    "rate" (Decimal percent), "taxable_cents" and "amount_cents" (ints).
    Raise _hold("source_values_conflict", ...) for a line that is not
    rate × taxable within the bill's rounding, or for central and state halves
    of the same rate and base that differ.
    """
    from decimal import ROUND_HALF_UP

    halves = {}
    for line in lines:
        expected = (line["rate"] * line["taxable_cents"] / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if abs(line["amount_cents"] - int(expected)) > 100:
            raise _hold("source_values_conflict", f"A {line['head'].upper()} line does not match its printed rate and taxable value.")
        if line["head"] in ("cgst", "sgst"):
            halves.setdefault((line["rate"], line["taxable_cents"]), {}).setdefault(line["head"], []).append(line["amount_cents"])
    for pair in halves.values():
        if "cgst" in pair and "sgst" in pair and sorted(pair["cgst"]) != sorted(pair["sgst"]):
            raise _hold("source_values_conflict", "Central and state tax on the same rate and value must be equal.")


class Bill:
    """A proposal bound to discovered identities; the single source of its plan."""

    def __init__(self, target, record, family, voucher_type, party, party_identity, lines, identities):
        document = record["document"]
        self.target, self.family, self.voucher_type, self.party = target, family, voucher_type, party
        self.kind, self.number, self.date = document["kind"], document["number"], document["date"]
        self.total_cents = _money(document["total"], "The bill total")
        self.lines = lines
        self.identities = {party: party_identity, **identities}
        self.series = "credit_note" if self.kind == "credit_note" else "invoice"
        self.identity = document_identity(party, self.number, date.fromisoformat(self.date), series=self.series)
        tax = sum(Decimal(str(ln["amount"])) for ln in record["voucher"]["lines"] if ln.get("role") == "tax")
        self.summary = {"vendor": party, "invoice_number": self.number, "date": self.date,
                        "total": document["total"], "tax": float(tax)}

    def accounting(self):
        """What two proposals for one document must agree on."""
        return json.dumps([self.family, self.voucher_type["GUID"], self.date, self.lines], sort_keys=True)

    def native_plan(self, remote_id, operation, expected):
        label = "credit note" if self.kind == "credit_note" else "bill"
        return {
            "format_version": FORMAT, "family": self.family, "operation": operation,
            "company": self.target["company"], "company_guid": self.target["references"]["company_guid"],
            "port": self.target.get("port") or 9000, "remote_id": remote_id, "voucher_type": self.voucher_type,
            "header": {"date": self.date, "reference": self.number, "party_ledger": self.party,
                       "narration": f"Minkops reviewed {label} {self.number}", "tag": None},
            "lines": self.lines,
            "references": {"company_guid": self.target["references"]["company_guid"], "ledgers": self.identities},
            "duplicate": {"strategy": "document", "families": list(KIND_FAMILIES[self.kind]) if self.kind == "invoice" else ["debit_note"],
                          "party_ledger": self.party, "number": self.number, "number_fields": ["REFERENCE"],
                          "window": invoice_window(date.fromisoformat(self.date))},
            "fence": "retry_after_read",
            "expected": {"guid": expected["guid"], "fingerprint": expected["fingerprint"]} if expected else None,
            "identity": {"version": 2, "series": self.series, "rule": "in_invoice_year", "hash": self.identity},
        }

    def preview(self):
        """What the reviewer sees will be entered, in native names."""
        return {"company": self.target["company"], "voucher_type": self.voucher_type["NAME"], "family": self.family,
                "date": self.date, "number": self.number, "party": self.party, "total": self.total_cents / 100,
                "lines": [{"ledger": ln["ledger"], "side": ln["side"], "amount": ln["amount_cents"] / 100} for ln in self.lines]}


def _document(record):
    document, voucher = record.get("document"), record.get("voucher")
    if not isinstance(document, dict) or not isinstance(voucher, dict):
        raise _hold("required_value_missing", "The bill needs a document and a proposed voucher.")
    if document.get("origin") != "domestic":
        raise _hold("identity_rule_unknown", "Only domestic supplier documents have a known invoice numbering year. Enter this bill in Tally.")
    number = document.get("number")
    if not isinstance(number, str) or not number.strip() or len(number) > 100:
        raise _hold("required_value_missing", "The bill's document number is missing.")
    try:
        date.fromisoformat(document.get("date") or "")
    except (TypeError, ValueError):
        raise _hold("required_value_missing", "The bill's date must be a calendar date.") from None
    if document.get("kind") not in KIND_FAMILIES or voucher.get("family") not in KIND_FAMILIES[document["kind"]]:
        raise _hold("classification_uncertain", "The voucher family must match the document: invoices are Purchase or Journal, supplier credit notes are Debit Notes.")
    _money(document.get("total"), "The bill total")
    return document, voucher


def summary(record, config):
    """The document summary every consumer reads; derived, never extracted."""
    document = record.get("document") or {}
    vendor = document.get("supplier_name")
    try:
        from .client_context import select_target

        party = (record.get("voucher") or {}).get("party") or {}
        if party.get("ledger_guid"):
            masters = _company(config, select_target(record, config["tally_target"]))
            vendor = masters.name(masters.one("LEDGER", party["ledger_guid"], "supplier_unresolved", ""))
    except (ValueError, KeyError, TypeError):
        pass
    tax = sum(Decimal(str(ln.get("amount", 0))) for ln in (record.get("voucher") or {}).get("lines", [])
              if isinstance(ln, dict) and ln.get("role") == "tax" and type(ln.get("amount")) in (int, float))
    return {"vendor": vendor, "invoice_number": document.get("number"), "date": document.get("date"),
            "total": document.get("total"), "tax": float(tax)}


def check(record, config, *, assume_new_supplier=False):
    """Bind a bill proposal to the routed company and enforce voucher rules.

    Returns a Bill, or raises a coded HoldReason (ValueError for routing). The
    AI chose every identity; this only proves each one is discovered, active,
    distinct and consistent with the bill's own printed values.
    """
    from .client_context import select_target

    scope = config["tally_target"]
    target = select_target(record, scope)
    document, voucher = _document(record)
    masters = _company(config, target)
    books_from = target.get("books_from")
    if books_from and document["date"] < books_from:
        raise _hold("date_before_books", f"Bill date {document['date']} is before {target['company']}'s books begin on "
                                         f"{books_from}; Tally cannot record it without a change to the company's books.")

    family = voucher["family"]
    voucher_type = masters.one("VOUCHERTYPE", voucher.get("voucher_type_guid"), "classification_uncertain",
                               "Select one discovered voucher type of the routed company.")
    if masters.family(voucher_type) != family or masters.scalar(voucher_type, "ISACTIVE").casefold() == "no":
        raise _hold("classification_uncertain", f"The voucher type must be an active {family.replace('_', ' ')} type.")
    if family == "purchase":
        if target.get("voucher_type_error"):
            raise _hold("voucher_type_unresolved", target["voucher_type_error"])
        if (target.get("voucher_type") or {}).get("GUID") != masters.scalar(voucher_type, "GUID"):
            raise _hold("classification_uncertain", "Purchases use the voucher type chosen for this run.")

    party = voucher.get("party") or {}
    if party.get("ledger_guid") is None:
        if party.get("new_supplier") is not True:
            raise _hold("supplier_unresolved", "Supplier match is unresolved; a new supplier has not been established.")
        if not assume_new_supplier:
            raise _hold("supplier_missing", f"Supplier '{document.get('supplier_name')}' is missing from the confirmed Tally "
                                            "ledgers. Create it, then continue this bill.")
        party_name, party_identity = document.get("supplier_name"), None
    else:
        ledger = masters.one("LEDGER", party["ledger_guid"], "supplier_unresolved", "The supplier must be one discovered ledger.")
        party_name, party_identity = masters.name(ledger), masters.identity(ledger)
    if not isinstance(party.get("evidence"), str) or not party["evidence"].strip():
        raise _hold("supplier_unresolved", "The supplier selection needs evidence.")

    raw = voucher.get("lines")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 39:
        raise _hold("unsupported_structure", "A bill voucher carries 1–39 lines besides the supplier.")
    lines, identities, taxes, tds, round_offs = [], {}, [], 0, 0
    for item in raw:
        if (not isinstance(item, dict) or item.get("role") not in LINE_ROLES or item.get("side") not in ("debit", "credit")
                or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()):
            raise _hold("source_values_conflict", "Each voucher line needs a known role, a side and bill evidence.")
        cents = _money(item.get("amount"), "Each line amount")
        ledger = masters.one("LEDGER", item.get("ledger_guid"), "classification_uncertain",
                             "Each line must select one discovered ledger of the routed company.")
        name = masters.name(ledger)
        if name == party_name or name in identities:
            raise _hold("classification_uncertain", "The supplier and every line need distinct ledgers.")
        identities[name] = masters.identity(ledger)
        allocation = None
        if item.get("cost_centre_guid") or item.get("cost_category_guid"):
            centre = masters.one("COSTCENTRE", item.get("cost_centre_guid"), "classification_uncertain", "Select one discovered cost centre.")
            category = masters.one("COSTCATEGORY", item.get("cost_category_guid"), "classification_uncertain", "Select one discovered cost category.")
            if masters.scalar(centre, "CATEGORY").casefold() != masters.name(category).casefold():
                raise _hold("classification_uncertain", "The cost centre does not belong to the selected cost category.")
            if masters.scalar(ledger, "ISCOSTCENTRESON").casefold() != "yes":
                raise _hold("classification_uncertain", f"{name} must enable cost centres in Tally before allocating it.")
            allocation = {"category": masters.name(category), "category_guid": masters.scalar(category, "GUID"),
                          "centre": masters.name(centre), "centre_guid": masters.scalar(centre, "GUID")}
        if item["role"] == "tds":
            tds += 1
        if item["role"] == "round_off":
            round_offs += 1
            if cents > ROUND_OFF_CAP_CENTS:
                raise _hold("source_values_conflict", "A round-off above one rupee is not a rounding difference.")
        if item["role"] == "tax":
            tax = item.get("tax")
            if (not isinstance(tax, dict) or tax.get("head") not in ("cgst", "sgst", "igst", "cess")
                    or type(tax.get("rate")) not in (int, float) or not 0 < tax["rate"] <= 100):
                raise _hold("source_values_conflict", "Each tax line needs its tax head and printed rate.")
            taxes.append({"head": tax["head"], "rate": Decimal(str(tax["rate"])), "amount_cents": cents,
                          "taxable_cents": _money(tax.get("taxable"), "The taxable value")})
        lines.append(_line(name, item["side"], cents, allocation))
    if tds:
        raise _hold("classification_uncertain", "TDS deductions need this company's confirmed posting profile. Enter this bill in Tally.")
    if round_offs > 1:
        raise _hold("source_values_conflict", "A bill has at most one round-off line.")
    _tax_consistent(taxes)
    party_cents = _money(document["total"], "The bill total")
    party_line = _line(party_name, PARTY_SIDE[family], party_cents)
    native = [party_line, *lines]
    if sum(ln["amount_cents"] for ln in native if ln["side"] == "debit") != sum(ln["amount_cents"] for ln in native if ln["side"] == "credit"):
        raise _hold("source_values_conflict", "The voucher lines must add up exactly to the printed total.")
    voucher_type_ref = {"NAME": masters.name(voucher_type), "GUID": masters.scalar(voucher_type, "GUID")}
    return Bill(target, record, family, voucher_type_ref, party_name, party_identity, native, identities)


class LegacyBill:
    """A proposal pinned to bill-entry 0.13 or earlier (fixed purchase fields).

    Its validation and plan formats are retained unchanged until those runs
    drain (MIN-155); new runs never reach this class.
    """

    def __init__(self, record, config, *, assume_new_supplier=False):
        from .bills import validate_tally
        from .client_context import select_target
        from .master_selection import resolve_masters

        scope = config["tally_target"]
        self.target = select_target(record, scope)
        resolve_masters(record, self.target, required=scope.get("master_selection_version") == 1,
                        allow_split=scope.get("tax_allocation_version") == 1)
        checked = self.target
        if assume_new_supplier:
            checked = {**self.target, "ledgers": [*self.target["ledgers"], record["data"].get("vendor")]}
        self.record = record
        self.identity = validate_tally(record["data"], checked, record.get("tax_allocations"))
        self.summary = record["data"]

    def _taxes(self):
        from .bills import allocation_entries

        return sorted(allocation_entries(self.record["data"], self.record.get("tax_allocations")), key=lambda t: t["ledger"])

    def accounting(self):
        return json.dumps([self.record["data"], self._taxes()], sort_keys=True, default=str)

    def native_plan(self, remote_id, operation, expected):
        from .bills import allocation_entries

        target, record = self.target, self.record
        plan = {"company": target["company"], "port": target["port"], "data": record["data"], "remote_id": remote_id,
                "operation": operation, "expected": expected if operation == "update" else None,
                "discovery_id": target["discovery_id"], "references": target.get("references")}
        if record.get("tax_allocations") is not None:
            plan.update(format_version=2, tax_allocations=allocation_entries(record["data"], record["tax_allocations"]))
        if target.get("voucher_type"):
            plan["references"] = {**plan["references"], "voucher_type": target["voucher_type"]}
            plan["format_version"] = 3
        return plan

    def preview(self):
        data = self.record["data"]
        lines = [{"ledger": data.get("vendor"), "side": "credit", "amount": data.get("total")},
                 {"ledger": data.get("purchase_ledger"), "side": "debit", "amount": data.get("subtotal")}]
        lines += [{"ledger": t["ledger"], "side": "debit", "amount": t["amount"]} for t in self._taxes()]
        return {"company": self.target.get("company"), "voucher_type": (self.target.get("voucher_type") or {}).get("NAME", "Purchase"),
                "family": "purchase", "date": data.get("date"), "number": data.get("invoice_number"),
                "party": data.get("vendor"), "total": data.get("total"), "lines": lines}


def resolve(record, config, *, assume_new_supplier=False):
    """The one gate every Tally bill decision passes: route, bind and validate."""
    if "voucher" in record:
        record["data"] = summary(record, config)
        return check(record, config, assume_new_supplier=assume_new_supplier)
    return LegacyBill(record, config, assume_new_supplier=assume_new_supplier)
