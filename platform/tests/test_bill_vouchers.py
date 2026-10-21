"""The bill gate: a proposal's identities bound to its company's pinned masters, its values checked against the bill."""

import copy
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
        self.assertIn("The lines come to 6355.00, but the bill's printed total is 6356.00.", message)
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
        self.assertIn("The lines claim 6355.00 of taxable value, but the bill prints 5560.00.", message)
        self.assertEqual(check(proposal(**printed)).lines[0]["amount_cents"], 635500)

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


if __name__ == "__main__":
    unittest.main()
