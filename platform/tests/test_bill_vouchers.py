"""The bill gate: a proposal's identities bound to its company's pinned masters, its values checked against the bill."""

import copy
import re
import unittest
from datetime import date

from minkops_platform.accounts import vouchers
from minkops_platform.accounts.vouchers import HoldReason

LEDGERS = [
    ("Acme Cement", "Sundry Creditors", "No"), ("Purchase 18%", "Purchase Accounts", "Yes"),
    ("Purchase 5%", "Purchase Accounts", "No"), ("Input CGST 9%", "Duties & Taxes", "No"),
    ("Input SGST 9%", "Duties & Taxes", "No"), ("Input CGST 2.5%", "Duties & Taxes", "No"),
    ("Input SGST 2.5%", "Duties & Taxes", "No"), ("Freight Inward", "Direct Expenses", "No"),
    ("Round Off", "Indirect Expenses", "No"), ("TDS Payable 194C", "Duties & Taxes", "No"),
    ("Electricity", "Indirect Expenses", "No"),
]
TYPES = [
    {"NAME": "Purchase", "@_RESERVEDNAME": "Purchase", "GUID": "vt-purchase"},
    {"NAME": "Purchase GST", "PARENT": "Purchase", "GUID": "vt-purchase-gst"},
    {"NAME": "Journal", "@_RESERVEDNAME": "Journal", "GUID": "vt-journal"},
    {"NAME": "Debit Note", "@_RESERVEDNAME": "Debit Note", "GUID": "vt-debit-note"},
    {"NAME": "Old Purchase", "PARENT": "Purchase", "GUID": "vt-old", "ISACTIVE": "No"},
    {"NAME": "Payment", "@_RESERVEDNAME": "Payment", "GUID": "vt-payment"},
]
COMPANY = {"name": "Test", "guid": "company", "books_from": date(2026, 4, 1), "tally_port": 9001}
REMOTE = "12345678-1234-5234-8234-123456789abc"


def guid(name, key="company"):
    base = name.lower().replace(" ", "-").replace("%", "pct") + "-guid"
    return base if key == "company" else f"{key}-{base}"


def view(key="company"):
    """A company's pinned mirror, in the shape mirror.company_view returns."""
    masters = [{"type": "LEDGER", "data": {"NAME": n, "GUID": guid(n, key), "PARENT": parent, "ALTERID": "5",
                                           "ISCOSTCENTRESON": costs}} for n, parent, costs in LEDGERS]
    # A supplier whose balance Tally keeps bill by bill.
    masters.append({"type": "LEDGER", "data": {"NAME": "Billwise Traders", "GUID": guid("Billwise Traders", key),
                                               "PARENT": "Sundry Creditors", "ALTERID": "5", "ISBILLWISEON": "Yes"}})
    # Stock: a purchase ledger that affects inventory, items in their units, and two godowns.
    masters.append({"type": "LEDGER", "data": {"NAME": "Purchase Stock 18%", "GUID": guid("Purchase Stock 18%", key),
                                               "PARENT": "Purchase Accounts", "ALTERID": "5", "AFFECTSSTOCK": "Yes"}})
    masters += [{"type": "UNIT", "data": {"NAME": name, "GUID": f"unit-{name}", "DECIMALPLACES": places,
                                          "ISSIMPLEUNIT": simple}}
                for name, places, simple in (("Bag", "0", "Yes"), ("MT", "3", "Yes"), ("Box of 10 Nos", "0", "No"))]
    masters += [{"type": "STOCKITEM", "data": {"NAME": name, "GUID": guid(name, key), "ALTERID": "7", "BASEUNITS": unit,
                                               "ISBATCHWISEON": batches}}
                for name, unit, batches in (("OPC Cement 53", "Bag", "No"), ("TMT Bar 12mm", "MT", "No"),
                                            ("Primer", "Bag", "Yes"), ("Anchor Bolts", "Box of 10 Nos", "No"))]
    masters += [{"type": "GODOWN", "data": {"NAME": name, "GUID": guid(name, key)}}
                for name in ("Main Location", "Site 4 Store")]
    masters += [{"type": "VOUCHERTYPE", "data": dict(t)} for t in TYPES]
    masters += [{"type": "COSTCATEGORY", "data": {"NAME": "Sites", "GUID": "cat-sites"}},
                {"type": "COSTCENTRE", "data": {"NAME": "Site 4", "GUID": "cc-site-4", "CATEGORY": "Sites"}},
                {"type": "COSTCENTRE", "data": {"NAME": "Head Office", "GUID": "cc-ho",
                                                "CATEGORY": "Primary Cost Category"}}]
    return {"company": "Test", "company_guid": key, "identity": {"NAME": "Test", "GUID": key},
            "masters": {"records": masters}}


def line(role, ledger, side, amount, *, tax=None, tds=None, centre=None):
    return {"role": role, "ledger_guid": guid(ledger), "side": side, "amount": amount, "tax": tax, "tds": tds,
            "cost_centre_guid": centre[0] if centre else None, "cost_category_guid": centre[1] if centre else None,
            "evidence": f"Printed {role} line"}


def proposal(**changes):
    """A two-rate GST bill with freight: taxable 5560.00, tax 795.00, total 6355.00."""
    record = {
        "bill": 1, "company_guid": "company", "company_evidence": "Buyer GSTIN matches Test.",
        "document": {"kind": "invoice", "number": "INV/26/0412", "date": "2026-10-14", "total": 6355.00,
                     "supplier_name": "ACME CEMENT", "supplier_gstin": "27AAACA1234A1Z5", "origin": "domestic",
                     "taxable": None, "tax": None},
        "voucher": {"family": "purchase", "voucher_type_guid": "vt-purchase-gst",
                    "party": {"ledger_guid": guid("Acme Cement"), "new_supplier": False,
                              "evidence": "GSTIN matches ledger."},
                    "lines": [
                        line("expense", "Purchase 18%", "debit", 4000.00),
                        line("expense", "Purchase 5%", "debit", 1500.00),
                        line("tax", "Input CGST 9%", "debit", 360.00, tax={"head": "cgst", "rate": 9, "taxable": 4000.00}),
                        line("tax", "Input SGST 9%", "debit", 360.00, tax={"head": "sgst", "rate": 9, "taxable": 4000.00}),
                        line("tax", "Input CGST 2.5%", "debit", 37.50,
                             tax={"head": "cgst", "rate": 2.5, "taxable": 1500.00}),
                        line("tax", "Input SGST 2.5%", "debit", 37.50,
                             tax={"head": "sgst", "rate": 2.5, "taxable": 1500.00}),
                        line("freight", "Freight Inward", "debit", 60.00),
                    ]},
        "supplier_details": None, "evidence": [{"field": "number", "page": 1, "quote": "Invoice No INV/26/0412"}],
        "exception": None,
    }
    for path, value in changes.items():
        target = record
        *parents, last = path.split(".")
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        target[int(last) if last.isdigit() else last] = value
    return record


def item(name, quantity, rate, amount, godowns, ledger="Purchase Stock 18%"):
    return {"item_guid": guid(name), "quantity": quantity, "rate": rate, "amount": amount, "ledger_guid": guid(ledger),
            "godowns": [{"godown_guid": guid(godown), "quantity": q, "amount": a} for godown, q, a in godowns],
            "evidence": f"Printed item line {name}"}


def stocked(*items, total=127440.00):
    """Cement and steel bought item-wise: taxable 108000.00, CGST and SGST 9720.00 each."""
    record = proposal(**{"document.total": total})
    record["voucher"]["items"] = list(items) or [
        item("OPC Cement 53", 100, 380, 38000.00, [("Main Location", 60, 22800.00), ("Site 4 Store", 40, 15200.00)]),
        item("TMT Bar 12mm", 1.25, 56000, 70000.00, [("Site 4 Store", 1.25, 70000.00)])]
    taxable = sum(entry["amount"] for entry in record["voucher"]["items"])
    record["voucher"]["lines"] = [
        line("tax", "Input CGST 9%", "debit", round(taxable * 0.09, 2), tax={"head": "cgst", "rate": 9, "taxable": taxable}),
        line("tax", "Input SGST 9%", "debit", round(taxable * 0.09, 2), tax={"head": "sgst", "rate": 9, "taxable": taxable})]
    return record


def check(record, **options):
    return vouchers.check(copy.deepcopy(record), view(), COMPANY, **options)


def held(record, **options):
    """The hold a proposal raises, as (code, message)."""
    try:
        check(record, **options)
    except HoldReason as refusal:
        return refusal.code, str(refusal)
    raise AssertionError("The proposal passed the gate.")


class BoundBillTest(unittest.TestCase):
    def test_a_multi_rate_bill_with_freight_binds_to_balanced_native_lines_and_one_plan(self):
        bill = check(proposal())
        self.assertEqual((bill.family, bill.voucher_type["NAME"], bill.party), ("purchase", "Purchase GST", "Acme Cement"))
        self.assertEqual(bill.lines[0], {"ledger": "Acme Cement", "side": "credit", "amount_cents": 635500,
                                         "allocation": None})
        self.assertEqual(sum(ln["amount_cents"] for ln in bill.lines if ln["side"] == "debit"), 635500)
        self.assertEqual(bill.identity, vouchers.document_identity("Acme Cement", "INV/26/0412", date(2026, 10, 14)))
        self.assertEqual(bill.destination_key, "bill:company")
        plan = bill.native_plan(REMOTE)
        self.assertEqual((plan["format_version"], plan["family"], plan["fence"], plan["port"]),
                         (6, "purchase", "retry_after_read", 9001))
        self.assertEqual(plan["header"], {"date": "2026-10-14", "reference": "INV/26/0412", "party_ledger": "Acme Cement",
                                          "narration": "Minkops reviewed bill INV/26/0412", "tag": None})
        self.assertEqual(plan["duplicate"]["families"], ["purchase", "journal"])
        self.assertEqual(plan["duplicate"]["window"], {"from": "2026-04-01", "to": "2027-03-31"})
        self.assertEqual(plan["references"]["ledgers"]["Freight Inward"],
                         {"GUID": guid("Freight Inward"), "PARENT": "Direct Expenses", "ALTERID": "5"})
        self.assertEqual(bill.preview()["lines"][0], {"ledger": "Acme Cement", "side": "credit", "amount": 6355.0})

    def test_a_printed_round_off_of_at_most_a_rupee_balances_the_bill(self):
        rounded = proposal(**{"document.total": 6355.40})
        rounded["voucher"]["lines"].append(line("round_off", "Round Off", "debit", 0.40))
        self.assertEqual(check(rounded).lines[0]["amount_cents"], 635540)
        too_large = proposal(**{"document.total": 6357.00})
        too_large["voucher"]["lines"].append(line("round_off", "Round Off", "debit", 2.00))
        twice = proposal(**{"document.total": 6355.40})
        twice["voucher"]["lines"] += [line("round_off", "Round Off", "debit", 0.20),
                                      line("round_off", "Electricity", "debit", 0.20)]
        for record in (too_large, twice):
            with self.subTest(lines=len(record["voucher"]["lines"])):
                self.assertEqual(held(record)[0], "source_values_conflict")

    def test_lines_short_of_the_printed_total_hold_and_say_by_how_much(self):
        code, message = held(proposal(**{"document.total": 6356.00}))
        self.assertEqual(code, "source_values_conflict")
        # The refusal names both figures, and that only a printed round-off may close a gap.
        self.assertIn("The lines come to 6,355.00, but the bill's printed total is 6,356.00.", message)
        self.assertIn("round-off the bill prints", message)

    def test_tax_lines_follow_their_printed_rate_and_central_and_state_halves_match(self):
        wrong_rate = proposal(**{"voucher.lines.2.amount": 400.00, "voucher.lines.3.amount": 400.00,
                                 "document.total": 6435.00})
        uneven = proposal(**{"voucher.lines.2.amount": 359.00, "voucher.lines.3.amount": 361.00})
        for record in (wrong_rate, uneven):
            with self.subTest(cgst=record["voucher"]["lines"][2]["amount"]):
                self.assertEqual(held(record)[0], "source_values_conflict")
        # Printed paise rounding of a tax amount is not a conflict.
        paise = proposal(**{"voucher.lines.4.amount": 37.49, "voucher.lines.5.amount": 37.49, "document.total": 6354.98})
        self.assertEqual(check(paise).lines[0]["amount_cents"], 635498)

    def test_printed_totals_expose_amounts_that_already_include_tax(self):
        # Booked from a tax-inclusive amount column, the bill balances with no tax lines at all: the input tax is lost.
        inclusive = proposal(**{"voucher.lines": [line("expense", "Purchase 18%", "debit", 4720.00),
                                                  line("expense", "Purchase 5%", "debit", 1575.00),
                                                  line("freight", "Freight Inward", "debit", 60.00)]})
        self.assertEqual(check(inclusive).lines[0]["amount_cents"], 635500)
        printed = {"document.taxable": 5560.00, "document.tax": 795.00}
        code, message = held({**inclusive, "document": {**inclusive["document"], "taxable": 5560.00, "tax": 795.00}})
        self.assertEqual(code, "source_values_conflict")
        self.assertIn("The lines claim 6,355.00 of taxable value, but the bill prints 5,560.00.", message)
        self.assertEqual(check(proposal(**printed)).lines[0]["amount_cents"], 635500)
        # A bill printing no tax at all (an exempt or unregistered supply) binds its lines to none.
        exempt = proposal(**{"document.total": 6355.00, "document.tax": 0, "voucher.lines": [
            line("expense", "Purchase 18%", "debit", 6355.00)]})
        self.assertEqual(check(exempt).lines[0]["amount_cents"], 635500)
        code, message = held({**inclusive, "document": {**inclusive["document"], "tax": 0},
                              "voucher": {**inclusive["voucher"], "lines": proposal()["voucher"]["lines"]}})
        self.assertIn("but the bill prints 0.00", message)

    def test_an_expense_bill_can_be_a_journal_and_a_supplier_credit_note_a_debit_note(self):
        journal = proposal(**{"voucher.family": "journal", "voucher.voucher_type_guid": "vt-journal",
                              "document.total": 1180.00, "voucher.lines": [
                                  line("expense", "Electricity", "debit", 1000.00),
                                  line("tax", "Input CGST 9%", "debit", 90.00,
                                       tax={"head": "cgst", "rate": 9, "taxable": 1000.00}),
                                  line("tax", "Input SGST 9%", "debit", 90.00,
                                       tax={"head": "sgst", "rate": 9, "taxable": 1000.00})]})
        bill = check(journal)
        # A Journal-booked bill is still found as a duplicate among Purchases, and the other way round.
        self.assertEqual((bill.family, bill.native_plan(REMOTE)["duplicate"]["families"]),
                         ("journal", ["purchase", "journal"]))
        note = proposal(**{"document.kind": "credit_note", "voucher.family": "debit_note",
                           "voucher.voucher_type_guid": "vt-debit-note"})
        for ln in note["voucher"]["lines"]:
            ln["side"] = "credit"
        credit = check(note)
        self.assertEqual(credit.lines[0]["side"], "debit")
        self.assertEqual(credit.identity, vouchers.document_identity("Acme Cement", "INV/26/0412", date(2026, 10, 14),
                                                                     series="credit_note"))
        self.assertEqual(credit.native_plan(REMOTE)["duplicate"]["families"], ["debit_note"])
        self.assertEqual(held(proposal(**{"document.kind": "credit_note"}))[0], "classification_uncertain")

    def test_cost_allocations_resolve_only_within_their_category_on_enabled_ledgers(self):
        allocated = proposal(**{"voucher.lines.0.cost_centre_guid": "cc-site-4",
                                "voucher.lines.0.cost_category_guid": "cat-sites"})
        self.assertEqual(check(allocated).lines[1]["allocation"], {"category": "Sites", "category_guid": "cat-sites",
                                                                   "centre": "Site 4", "centre_guid": "cc-site-4"})
        other_category = proposal(**{"voucher.lines.0.cost_centre_guid": "cc-ho",
                                     "voucher.lines.0.cost_category_guid": "cat-sites"})
        disabled_ledger = proposal(**{"voucher.lines.1.cost_centre_guid": "cc-site-4",
                                      "voucher.lines.1.cost_category_guid": "cat-sites"})
        for record in (other_category, disabled_ledger):
            with self.subTest(centre=record["voucher"]["lines"][0]["cost_centre_guid"]):
                self.assertEqual(held(record)[0], "classification_uncertain")

    def test_identities_come_only_from_the_routed_company(self):
        cases = {
            "another company's ledger": proposal(**{"voucher.lines.6.ledger_guid": guid("Freight Inward", "other")}),
            "a payment type": proposal(**{"voucher.voucher_type_guid": "vt-payment"}),
            "an inactive type": proposal(**{"voucher.voucher_type_guid": "vt-old"}),
            "a ledger used twice": proposal(**{"voucher.lines.6.ledger_guid": guid("Purchase 18%")}),
            "the supplier as a line": proposal(**{"voucher.lines.6.ledger_guid": guid("Acme Cement")}),
        }
        for case, record in cases.items():
            with self.subTest(case):
                self.assertIn(held(record)[0], ("voucher_type_unresolved", "classification_uncertain"))

    def test_tds_follows_its_section_and_rate_and_reduces_only_what_the_supplier_is_owed(self):
        tds = {"section": "194C", "rate": 1}
        deducted = proposal()
        deducted["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "credit", 55.00, tds=tds))
        bill = check(deducted)
        # One percent of the 5,500.00 contract value, never of GST or freight.
        self.assertEqual(bill.lines[0], {"ledger": "Acme Cement", "side": "credit", "amount_cents": 630000,
                                         "allocation": None})
        wrong = proposal()
        wrong["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "credit", 63.55, tds=tds))
        backwards = proposal()
        backwards["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "debit", 55.00, tds=tds))
        unstated = proposal()
        unstated["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "credit", 55.00))
        self.assertEqual(held(wrong)[0], "source_values_conflict")
        self.assertEqual(held(backwards)[0], "classification_uncertain")
        self.assertEqual(held(unstated)[0], "classification_uncertain")

    def test_suppliers_documents_and_dates_the_gate_cannot_book_hold_with_their_reasons(self):
        new = proposal(**{"voucher.party": {"ledger_guid": None, "new_supplier": True, "evidence": "No GSTIN match."}})
        cases = ((new, {}, "supplier_missing"),
                 (proposal(**{"voucher.party.ledger_guid": None}), {}, "supplier_unresolved"),
                 (proposal(**{"document.origin": "foreign"}), {}, "identity_rule_unknown"),
                 (proposal(**{"document.date": "2026-03-31"}), {}, "date_before_books"),
                 (proposal(), {"until": "2026-09-30"}, "date_outside_company_period"))
        for record, options, code in cases:
            with self.subTest(code=code):
                self.assertEqual(held(record, **options)[0], code)
        self.assertIn("has no ledger in Test. Create it, then this bill can be saved.", held(new)[1])
        # Once a person approves creating it, the printed name is the supplier's ledger.
        created = check(new, assume_new_supplier=True)
        self.assertEqual((created.party, created.identity),
                         ("ACME CEMENT", vouchers.document_identity("Acme Cement", "INV/26/0412", date(2026, 10, 14))))

    def test_a_bill_by_bill_supplier_is_owed_a_new_reference_named_by_the_invoice(self):
        billwise = {"voucher.party.ledger_guid": guid("Billwise Traders")}
        plan = check(proposal(**billwise)).native_plan(REMOTE)
        party = plan["lines"][0]
        self.assertEqual((plan["format_version"], party["ledger"], party["bills"]), (6, "Billwise Traders", [
            {"name": "INV/26/0412", "type": "New Ref", "amount_cents": party["amount_cents"]}]))
        # Other suppliers' lines carry no reference.
        self.assertNotIn("bills", check(proposal()).native_plan(REMOTE)["lines"][0])
        # A debit note adjusts a bill it would have to name; that is entered in Tally.
        note = proposal(**billwise, **{"document.kind": "credit_note", "voucher.family": "debit_note",
                                       "voucher.voucher_type_guid": "vt-debit-note"})
        note["voucher"]["lines"] = [{**line, "side": "credit"} for line in note["voucher"]["lines"]]
        self.assertEqual(held(note)[0], "unsupported_structure")

    def test_a_bill_booked_item_wise_carries_each_item_to_its_godowns_and_purchase_ledger(self):
        bill = check(stocked())
        plan = bill.native_plan(REMOTE)
        # Tally books the items' value on their purchase ledger: one line for both items, as its readback reports.
        self.assertEqual([(ln["ledger"], ln["side"], ln["amount_cents"]) for ln in plan["lines"]], [
            ("Acme Cement", "credit", 12744000), ("Purchase Stock 18%", "debit", 10800000),
            ("Input CGST 9%", "debit", 972000), ("Input SGST 9%", "debit", 972000)])
        self.assertEqual(plan["inventory"], [
            {"item": "OPC Cement 53", "unit": "Bag", "quantity": "100", "rate": "380", "side": "debit",
             "amount_cents": 3800000, "ledger": "Purchase Stock 18%", "godowns": [
                 {"godown": "Main Location", "quantity": "60", "amount_cents": 2280000},
                 {"godown": "Site 4 Store", "quantity": "40", "amount_cents": 1520000}]},
            {"item": "TMT Bar 12mm", "unit": "MT", "quantity": "1.25", "rate": "56000", "side": "debit",
             "amount_cents": 7000000, "ledger": "Purchase Stock 18%", "godowns": [
                 {"godown": "Site 4 Store", "quantity": "1.25", "amount_cents": 7000000}]}])
        self.assertEqual(plan["references"]["stock_items"]["TMT Bar 12mm"],
                         {"GUID": guid("TMT Bar 12mm"), "BASEUNITS": "MT"})
        self.assertEqual(plan["references"]["godowns"], {"Main Location": {"GUID": guid("Main Location")},
                                                         "Site 4 Store": {"GUID": guid("Site 4 Store")}})
        self.assertEqual(bill.booking, {"voucher_type": {"NAME": "Purchase GST", "GUID": "vt-purchase-gst"},
                                        "ledgers": ["Purchase Stock 18%"], "items": True})
        # A bill booked to ledgers carries no inventory, and its booking says so.
        self.assertNotIn("inventory", check(proposal()).native_plan(REMOTE))
        self.assertEqual(check(proposal()).booking["ledgers"], ["Freight Inward", "Purchase 18%", "Purchase 5%"])

    def test_items_tally_cannot_take_as_proposed_hold_with_their_reasons(self):
        cement = item("OPC Cement 53", 100, 380, 38000.00, [("Main Location", 100, 38000.00)])
        cases = {
            "batches": (stocked(item("Primer", 100, 380, 38000.00, [("Main Location", 100, 38000.00)])),
                        "unsupported_structure", "Primer tracks batches"),
            "compound unit": (stocked(item("Anchor Bolts", 100, 380, 38000.00, [("Main Location", 100, 38000.00)])),
                              "unsupported_structure", "Anchor Bolts is counted in a compound unit"),
            "rate times quantity": (stocked(item("OPC Cement 53", 100, 390, 38000.00, [("Main Location", 100, 38000.00)])),
                                    "source_values_conflict", "100 at 390 comes to 39,000.00"),
            "fractional bags": (stocked(item("OPC Cement 53", 100.5, 378.11, 38000.00,
                                             [("Main Location", 100.5, 38000.00)])),
                                "source_values_conflict", "OPC Cement 53 is counted in Bag to 0 decimal places"),
            "godowns short": (stocked(item("OPC Cement 53", 100, 380, 38000.00, [("Main Location", 90, 34200.00)])),
                              "classification_uncertain", "OPC Cement 53's godowns must take its 100 Bag and 38,000.00"),
            "ledger without stock": (stocked(item("OPC Cement 53", 100, 380, 38000.00, [("Main Location", 100, 38000.00)],
                                                  ledger="Purchase 18%")),
                                     "classification_uncertain", "Purchase 18% must have inventory values affected"),
        }
        for case, (record, code, reason) in cases.items():
            with self.subTest(case):
                found = held(record)
                self.assertEqual(found[0], code)
                self.assertIn(reason, found[1])
        # Items are bought on a Purchase invoice; an item ledger is the items' own line.
        journal = stocked(cement, total=44840.00)
        journal["voucher"].update(family="journal", voucher_type_guid="vt-journal")
        self.assertEqual(held(journal)[0], "unsupported_structure")
        doubled = stocked(cement, total=44840.00)
        doubled["voucher"]["lines"].append(line("expense", "Purchase Stock 18%", "debit", 100.00))
        self.assertEqual(held(doubled)[0], "classification_uncertain")

    def test_values_the_bill_did_not_give_or_gave_malformed_never_reach_a_plan(self):
        # An unread origin is a missing value, not a foreign supplier.
        self.assertEqual(held(proposal(**{"document.origin": None})),
                         ("required_value_missing", "The bill's origin must be read from it."))
        self.assertEqual(held(proposal(**{"document.number": " ", "document.total": None}))[1],
                         "The bill's number, total must be read from it.")
        self.assertEqual(held(proposal(document=None))[0], "required_value_missing")
        for record in (proposal(**{"voucher.lines.0.amount": 4000.001}), proposal(**{"voucher.lines.0.amount": -4000.00}),
                       proposal(**{"voucher.lines.0.side": "sideways"}), proposal(**{"document.date": "14/10/2026"})):
            with self.subTest(line=record["voucher"]["lines"][0], date=record["document"]["date"]):
                self.assertIn(held(record)[0], ("source_values_conflict", "required_value_missing"))


# A GST-registered company as TallyPrime keeps it: GST switched on, a registration as a tax unit, tax ledgers marked
# as GST duties with their heads and rates, and a supplier whose ledger holds its registration and mailing state.
BUYER, ACME = "27ABCDE1234F1Z5", "27AAACA1234A1Z5"


def gst_view(*, registrations=(("Test Maharashtra", BUYER),), supplier=ACME):
    gst = view()
    gst["identity"] = {**gst["identity"], "ISGSTON": "Yes", "STATENAME": "Maharashtra"}
    for record in gst["masters"]["records"]:
        data = record["data"]
        match = re.fullmatch(r"Input ([CS])GST ([\d.]+)%", data.get("NAME", ""))
        if match:
            data.update(TAXTYPE="GST", GSTDUTYHEAD="CGST" if match[1] == "C" else "SGST/UTGST", RATEOFTAXCALCULATION=match[2])
        if data.get("NAME") == "Acme Cement" and supplier:
            data["LEDGSTREGDETAILS.LIST"] = [{"APPLICABLEFROM": "20170701", "GSTIN": supplier, "GSTREGISTRATIONTYPE": "Regular",
                                              "PLACEOFSUPPLY": "Maharashtra"}]
            data["LEDMAILINGDETAILS.LIST"] = {"APPLICABLEFROM": "20170701", "STATE": "Maharashtra", "COUNTRY": "India"}
    gst["masters"]["records"] += [{"type": "TAXUNIT", "data": {"@_NAME": name, "GSTREGNUMBER": number}}
                                  for name, number in registrations]
    return gst


def gst_proposal(**changes):
    """The two-rate bill with its lines' GST rates and supply: freight is untaxed."""
    record = proposal(**{"voucher.lines.0.gst_rate": 18, "voucher.lines.0.supply": "goods",
                         "voucher.lines.1.gst_rate": 5, "voucher.lines.1.supply": "goods",
                         "voucher.lines.6.gst_rate": 0, **changes})
    return record


def gst_check(record, **options):
    return vouchers.check(copy.deepcopy(record), options.pop("in_view", None) or gst_view(), COMPANY, **options)


def gst_held(record, **options):
    try:
        gst_check(record, **options)
    except HoldReason as refusal:
        return refusal.code, str(refusal)
    raise AssertionError("The proposal passed the gate.")


class GstReturnsTest(unittest.TestCase):
    """What a purchase into a GST-registered company states for Tally's returns, and the GST checks before it."""

    def test_a_purchase_states_the_suppliers_registration_the_place_of_supply_and_each_taxed_lines_rates(self):
        bound = gst_check(gst_proposal())
        plan = bound.native_plan(REMOTE)
        self.assertEqual(plan["gst"], {"party": {"gstin": ACME, "registration_type": "Regular", "state": "Maharashtra",
                                                 "country": "India", "place_of_supply": "Maharashtra"},
                                       "company_gstin": BUYER, "registration": None})
        stated = {ln["ledger"]: ln.get("gst") for ln in plan["lines"]}
        self.assertEqual(stated["Purchase 18%"], {"taxability": "Taxable", "supply": "Goods",
                                                  "rates": {"cgst": "9", "sgst": "9", "igst": "18", "cess": "0"}})
        self.assertEqual(stated["Purchase 5%"]["rates"], {"cgst": "2.5", "sgst": "2.5", "igst": "5", "cess": "0"})
        # The untaxed freight, the tax lines and the supplier state nothing of their own.
        self.assertEqual({ln for ln, details in stated.items() if details}, {"Purchase 18%", "Purchase 5%"})
        self.assertEqual(bound.notes, [])
        # A company without GST switched on states nothing for returns, whatever the bill charges.
        self.assertNotIn("gst", check(proposal()).native_plan(REMOTE))

    def test_each_taxed_line_carries_a_rate_the_bills_tax_lines_charge(self):
        one = proposal(**{"voucher.lines": [line("expense", "Purchase 18%", "debit", 5000.00),
                                            line("tax", "Input CGST 9%", "debit", 450.00, tax={"head": "cgst", "rate": 9, "taxable": 5000.00}),
                                            line("tax", "Input SGST 9%", "debit", 450.00, tax={"head": "sgst", "rate": 9, "taxable": 5000.00})],
                          "document.total": 5900.00, "voucher.lines.0.gst_rate": None, "voucher.lines.0.supply": "services"})
        # At one rate, every line that does not say otherwise is taxed at it.
        [taxed] = [ln for ln in gst_check(one).native_plan(REMOTE)["lines"] if ln.get("gst")]
        self.assertEqual((taxed["ledger"], taxed["gst"]["supply"], taxed["gst"]["rates"]["igst"]), ("Purchase 18%", "Services", "18"))
        # At several, each line says its own, and the lines at each rate must come to the value taxed at it.
        self.assertIn("more than one GST rate", gst_held(proposal())[1])
        code, reason = gst_held(gst_proposal(**{"voucher.lines.0.gst_rate": 5, "voucher.lines.1.gst_rate": 18}))
        self.assertEqual(code, "source_values_conflict")
        self.assertIn("taxed at 18% come to 1500.00", reason)
        self.assertIn("rate the bill's tax lines charge", gst_held(gst_proposal(**{"voucher.lines.6.gst_rate": 12}))[1])
        # Goods or services: the line says, or its ledger does in Tally.
        self.assertEqual(gst_held(gst_proposal(**{"voucher.lines.0.supply": None}))[0], "classification_uncertain")
        typed = gst_view()
        next(r for r in typed["masters"]["records"] if r["data"].get("NAME") == "Purchase 18%")["data"]["GSTTYPEOFSUPPLY"] = "Goods"
        self.assertTrue(gst_check(gst_proposal(**{"voucher.lines.0.supply": None}), in_view=typed))

    def test_of_several_registrations_the_bill_names_the_one_it_is_addressed_to(self):
        several = gst_view(registrations=(("Test Maharashtra", BUYER), ("Test Karnataka", "29ABCDE1234F1Z1")))
        self.assertIn("give the buyer GSTIN", gst_held(gst_proposal(), in_view=several)[1])
        self.assertEqual(gst_held(gst_proposal(**{"document.buyer_gstin": "07ABCDE1234F1Z9"}), in_view=several)[0],
                         "company_unresolved")
        plan = gst_check(gst_proposal(**{"document.buyer_gstin": "29abcde1234f1z1"}), in_view=several).native_plan(REMOTE)
        self.assertEqual(plan["gst"]["registration"], {"name": "Test Karnataka", "gstin": "29ABCDE1234F1Z1"})
        # Addressed to the Karnataka registration from a Maharashtra supplier, the supply is inter-state.
        self.assertEqual(plan["gst"]["party"]["place_of_supply"], "Karnataka")

    def test_tax_heads_the_supplys_states_rule_out_go_to_a_person(self):
        igst = proposal(**{"voucher.lines": [line("expense", "Purchase 18%", "debit", 5000.00, ),
                                             line("tax", "Electricity", "debit", 900.00, tax={"head": "igst", "rate": 18, "taxable": 5000.00})],
                           "document.total": 5900.00, "voucher.lines.0.supply": "goods"})
        [note] = gst_check(igst).notes
        self.assertIn("charges IGST, but its supplier and place of supply are both in Maharashtra", note)
        # CGST and SGST on a supply printed as delivered to another state.
        [note] = gst_check(gst_proposal(**{"document.place_of_supply": "Karnataka (29)"})).notes
        self.assertIn("its supplier is in Maharashtra and its place of supply is in Karnataka, where IGST applies", note)
        self.assertEqual(gst_check(gst_proposal(**{"document.place_of_supply": "Maharashtra"})).notes, [])
        self.assertEqual(gst_held(gst_proposal(**{"document.place_of_supply": "Atlantis"}))[0], "source_values_conflict")

    def test_a_tax_line_is_carried_by_a_ledger_for_its_head_and_rate(self):
        # Tally marks a GST duty ledger with its head and rate.
        swapped = gst_proposal(**{"voucher.lines.2.ledger_guid": guid("Input SGST 9%"),
                                  "voucher.lines.3.ledger_guid": guid("Input CGST 9%")})
        self.assertEqual(gst_held(swapped), ("classification_uncertain", "Input SGST 9% is a SGST/UTGST ledger in Tally, so "
                                             "it cannot carry CGST at 9%. Choose the CGST ledger."))
        rated = gst_proposal(**{"voucher.lines.4.ledger_guid": guid("Input CGST 9%"), "voucher.lines.2.ledger_guid": guid("Input CGST 2.5%")})
        self.assertIn("Input CGST 2.5% is set to 2.5% in Tally, but the bill charges CGST at 9%", gst_held(rated)[1])
        # A ledger Tally does not mark is read by what its name claims; a central or state ledger may name the combined rate.
        self.assertIn("named for SGST", held(proposal(**{"voucher.lines.2.ledger_guid": guid("Input SGST 9%"),
                                                          "voucher.lines.3.ledger_guid": guid("Input CGST 9%")}))[1])
        self.assertIn("named for another rate", held(proposal(**{"voucher.lines.4.ledger_guid": guid("Input CGST 9%"),
                                                                 "voucher.lines.2.ledger_guid": guid("Input CGST 2.5%")}))[1])
        combined = view()
        for record in combined["masters"]["records"]:
            if record["data"]["NAME"] in ("Input CGST 9%", "Input SGST 9%"):
                record["data"]["NAME"] = record["data"]["NAME"].replace("9%", "18%")
        self.assertTrue(vouchers.check(copy.deepcopy(proposal()), combined, COMPANY))

    def test_a_bills_supplier_gstin_is_its_ledgers(self):
        self.assertEqual(gst_held(gst_proposal(**{"document.supplier_gstin": "27AAACZ9999Z1Z9"}))[0], "supplier_unresolved")

    def test_tally_is_told_only_what_it_can_use(self):
        # A supplier whose ledger has no GSTIN: Tally cannot claim the bill's tax, and the person is told why.
        unregistered = gst_check(gst_proposal(), in_view=gst_view(supplier=None))
        self.assertNotIn("gst", unregistered.native_plan(REMOTE))
        self.assertEqual(unregistered.notes, ["Tally's GST returns cannot claim this bill's tax: Acme Cement has no GSTIN in "
                                              "Tally. Add the supplier's GSTIN to its ledger there."])
        # An item-wise purchase states the supplier's registration; its items' rates are Tally's own.
        items = gst_check(stocked()).native_plan(REMOTE)
        self.assertEqual(items["gst"]["party"]["gstin"], ACME)
        self.assertFalse(any(ln.get("gst") for ln in items["lines"]))
        # A debit note states the supplier's registration too; a journal, neither.
        note = gst_proposal(**{"document.kind": "credit_note", "voucher.family": "debit_note",
                               "voucher.voucher_type_guid": "vt-debit-note"})
        for ln in note["voucher"]["lines"]:
            ln["side"] = "credit"
        debit = gst_check(note).native_plan(REMOTE)
        self.assertEqual((debit["gst"]["party"]["gstin"], any(ln.get("gst") for ln in debit["lines"])), (ACME, False))
        journal = gst_check(gst_proposal(**{"voucher.family": "journal", "voucher.voucher_type_guid": "vt-journal"}))
        self.assertNotIn("gst", journal.native_plan(REMOTE))


if __name__ == "__main__":
    unittest.main()
