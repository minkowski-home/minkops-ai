"""Bill proposals as N-line vouchers: identities from discovery, rules in code, values from the bill."""

import copy
import unittest
from datetime import date

from minkops_platform.accounts import vouchers
from minkops_platform.accounts.bills import HoldReason
from minkops_platform.accounts.client_context import targets_from_snapshot

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


def guid(name):
    return name.lower().replace(" ", "-").replace("%", "pct") + "-guid"


def company(name="Test", key="company"):
    masters = [{"type": "LEDGER", "data": {"NAME": n, "GUID": guid(n) if key == "company" else f"{key}-{guid(n)}",
                                           "PARENT": parent, "ALTERID": "5", "ISCOSTCENTRESON": costs}}
               for n, parent, costs in LEDGERS]
    masters += [{"type": "VOUCHERTYPE", "data": dict(t)} for t in TYPES]
    masters += [{"type": "COSTCATEGORY", "data": {"NAME": "Sites", "GUID": "cat-sites"}},
                {"type": "COSTCENTRE", "data": {"NAME": "Site 4", "GUID": "cc-site-4", "CATEGORY": "Sites"}},
                {"type": "COSTCENTRE", "data": {"NAME": "Head Office", "GUID": "cc-ho", "CATEGORY": "Primary Cost Category"}}]
    return {"company": name, "company_guid": key, "port": 9000, "status": "ready",
            "identity": {"NAME": name, "GUID": key, "BOOKSFROM": "20260401"},
            "masters": {"status": "ready", "count": len(masters), "records": masters},
            "vouchers": {"status": "ready", "count": 0, "records": []}}


def config(*companies):
    companies = companies or (company(),)
    snapshot = {"format_version": "2", "period": {"from": "2026-04-01", "to": "2026-10-31"}, "companies": list(companies)}
    targets = targets_from_snapshot(snapshot, "device", "discovery")
    for target in targets:
        pinned = next(c for c in target["purchase_voucher_types"] if c["name"] == "Purchase GST")
        target["voucher_type"] = pinned["identity"]
    return {"tally_target": {"device_id": "device", "discovery_id": "discovery", "companies": targets,
                             "company_mode": "infer", "locked_company_guid": None},
            "source_catalog_snapshot": {"sources": [{"tool": "tally", "key": "tally", "snapshot": snapshot}]}}


def line(role, ledger, side, amount, *, tax=None, centre=None):
    return {"role": role, "ledger_guid": guid(ledger), "side": side, "amount": amount, "tax": tax,
            "cost_centre_guid": centre[0] if centre else None, "cost_category_guid": centre[1] if centre else None,
            "evidence": f"Printed {role} line"}


def proposal(**changes):
    """A two-rate GST bill with freight: total 6355.00."""
    record = {
        "source_file_id": "bill-1", "operation": "append", "company_guid": "company",
        "company_evidence": "Buyer GSTIN matches Test.",
        "document": {"kind": "invoice", "number": "INV/26/0412", "date": "2026-10-14", "total": 6355.00,
                     "supplier_name": "ACME CEMENT", "supplier_gstin": "27AAACA1234A1Z5", "origin": "domestic"},
        "voucher": {"family": "purchase", "voucher_type_guid": "vt-purchase-gst",
                    "party": {"ledger_guid": guid("Acme Cement"), "new_supplier": False, "evidence": "GSTIN matches ledger."},
                    "lines": [
                        line("expense", "Purchase 18%", "debit", 4000.00),
                        line("expense", "Purchase 5%", "debit", 1500.00),
                        line("tax", "Input CGST 9%", "debit", 360.00, tax={"head": "cgst", "rate": 9, "taxable": 4000.00}),
                        line("tax", "Input SGST 9%", "debit", 360.00, tax={"head": "sgst", "rate": 9, "taxable": 4000.00}),
                        line("tax", "Input CGST 2.5%", "debit", 37.50, tax={"head": "cgst", "rate": 2.5, "taxable": 1500.00}),
                        line("tax", "Input SGST 2.5%", "debit", 37.50, tax={"head": "sgst", "rate": 2.5, "taxable": 1500.00}),
                        line("freight", "Freight Inward", "debit", 60.00),
                    ]},
        "evidence": [{"field": "number", "page": 1, "quote": "Invoice No INV/26/0412"}],
        "exceptions": [], "findings": [],
    }
    for path, value in changes.items():
        target = record
        *parents, last = path.split(".")
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        target[int(last) if last.isdigit() else last] = value
    return record


class ResolvedBillTest(unittest.TestCase):
    def test_a_multi_rate_bill_with_freight_resolves_to_balanced_native_lines(self):
        bill = vouchers.check(proposal(), config())
        self.assertEqual((bill.family, bill.voucher_type["NAME"], bill.party), ("purchase", "Purchase GST", "Acme Cement"))
        self.assertEqual(bill.lines[0], {"ledger": "Acme Cement", "side": "credit", "amount_cents": 635500, "allocation": None})
        self.assertEqual(sum(ln["amount_cents"] for ln in bill.lines if ln["side"] == "debit"), 635500)
        self.assertEqual(bill.identity, vouchers.document_identity("Acme Cement", "INV/26/0412", date(2026, 10, 14)))
        self.assertEqual(bill.summary, {"vendor": "Acme Cement", "invoice_number": "INV/26/0412", "date": "2026-10-14",
                                        "total": 6355.0, "tax": 795.0})
        plan = bill.native_plan("12345678-1234-5234-8234-123456789abc", "append", None)
        self.assertEqual((plan["format_version"], plan["family"], plan["fence"]), (5, "purchase", "retry_after_read"))
        self.assertEqual(plan["duplicate"]["families"], ["purchase", "journal"])
        self.assertEqual(plan["duplicate"]["window"], {"from": "2026-04-01", "to": "2027-03-31"})
        self.assertEqual(plan["references"]["ledgers"]["Freight Inward"], {"GUID": guid("Freight Inward"), "PARENT": "Direct Expenses", "ALTERID": "5"})
        self.assertIs(vouchers.upgrade(plan, identity=bill.identity), plan)

    def test_a_printed_round_off_balances_the_bill_within_one_rupee(self):
        rounded = proposal(**{"document.total": 6355.40})
        rounded["voucher"]["lines"].append(line("round_off", "Round Off", "debit", 0.40))
        self.assertEqual(vouchers.check(rounded, config()).lines[0]["amount_cents"], 635540)
        too_large = proposal(**{"document.total": 6357.00})
        too_large["voucher"]["lines"].append(line("round_off", "Round Off", "debit", 2.00))
        twice = proposal(**{"document.total": 6355.40})
        twice["voucher"]["lines"] += [line("round_off", "Round Off", "debit", 0.20), line("round_off", "Round Off", "debit", 0.20)]
        for record in (too_large, twice):
            with self.subTest(record=record["voucher"]["lines"][-1]), self.assertRaises(HoldReason):
                vouchers.check(record, config())

    def test_lines_that_do_not_reach_the_printed_total_hold(self):
        with self.assertRaises(HoldReason) as held:
            vouchers.check(proposal(**{"document.total": 6400.00}), config())
        self.assertEqual(held.exception.code, "source_values_conflict")

    def test_tax_lines_must_follow_their_rate_and_split_evenly(self):
        wrong_rate = proposal(**{"voucher.lines.2.amount": 400.00, "voucher.lines.3.amount": 400.00, "document.total": 6435.00})
        uneven = proposal(**{"voucher.lines.2.amount": 359.00, "voucher.lines.3.amount": 361.00})
        paise = proposal(**{"voucher.lines.4.amount": 37.49, "voucher.lines.5.amount": 37.49, "document.total": 6354.98})
        for record, code in ((wrong_rate, "source_values_conflict"), (uneven, "source_values_conflict")):
            with self.subTest(code=code), self.assertRaises(HoldReason) as held:
                vouchers.check(record, config())
            self.assertEqual(held.exception.code, code)
        self.assertEqual(vouchers.check(paise, config()).summary["tax"], 794.98)

    def test_an_expense_bill_can_be_a_journal_and_a_supplier_credit_note_a_debit_note(self):
        journal = proposal(**{"voucher.family": "journal", "voucher.voucher_type_guid": "vt-journal", "document.total": 1180.00,
                              "voucher.lines": [line("expense", "Electricity", "debit", 1000.00),
                                                line("tax", "Input CGST 9%", "debit", 90.00, tax={"head": "cgst", "rate": 9, "taxable": 1000.00}),
                                                line("tax", "Input SGST 9%", "debit", 90.00, tax={"head": "sgst", "rate": 9, "taxable": 1000.00})]})
        bill = vouchers.check(journal, config())
        self.assertEqual((bill.family, bill.native_plan("12345678-1234-5234-8234-123456789abc", "append", None)["duplicate"]["families"]),
                         ("journal", ["purchase", "journal"]))
        note = proposal(**{"document.kind": "credit_note", "voucher.family": "debit_note", "voucher.voucher_type_guid": "vt-debit-note"})
        for ln in note["voucher"]["lines"]:
            ln["side"] = "credit"
        credit = vouchers.check(note, config())
        self.assertEqual(credit.lines[0]["side"], "debit")
        self.assertEqual(credit.identity, vouchers.document_identity("Acme Cement", "INV/26/0412", date(2026, 10, 14), series="credit_note"))
        plan = credit.native_plan("12345678-1234-5234-8234-123456789abc", "append", None)
        self.assertEqual(plan["duplicate"]["families"], ["debit_note"])
        mismatched = proposal(**{"document.kind": "credit_note"})
        with self.assertRaises(HoldReason):
            vouchers.check(mismatched, config())

    def test_cost_allocations_resolve_only_within_their_category_on_enabled_ledgers(self):
        allocated = proposal(**{"voucher.lines.0.cost_centre_guid": "cc-site-4", "voucher.lines.0.cost_category_guid": "cat-sites"})
        bill = vouchers.check(allocated, config())
        self.assertEqual(bill.lines[1]["allocation"], {"category": "Sites", "category_guid": "cat-sites", "centre": "Site 4", "centre_guid": "cc-site-4"})
        for record in (proposal(**{"voucher.lines.0.cost_centre_guid": "cc-ho", "voucher.lines.0.cost_category_guid": "cat-sites"}),
                       proposal(**{"voucher.lines.1.cost_centre_guid": "cc-site-4", "voucher.lines.1.cost_category_guid": "cat-sites"})):
            with self.assertRaises(HoldReason):
                vouchers.check(record, config())

    def test_identities_come_only_from_the_routed_company_and_its_pinned_choices(self):
        other = company("Other", "other")
        foreign_ledger = proposal(**{"voucher.lines.6.ledger_guid": "other-" + guid("Freight Inward")})
        wrong_type = proposal(**{"voucher.voucher_type_guid": "vt-payment"})
        unpinned = proposal(**{"voucher.voucher_type_guid": "vt-purchase"})
        inactive = proposal(**{"voucher.voucher_type_guid": "vt-old"})
        repeated = proposal(**{"voucher.lines.6.ledger_guid": guid("Purchase 18%")})
        for record in (foreign_ledger, wrong_type, unpinned, inactive, repeated):
            with self.subTest(voucher=record["voucher"]["voucher_type_guid"]), self.assertRaises(HoldReason):
                vouchers.check(record, config(company(), other))

    def test_tds_waits_for_a_confirmed_posting_profile(self):
        record = proposal(**{"document.total": 6355.00})
        record["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "credit", 40.00))
        with self.assertRaises(HoldReason) as held:
            vouchers.check(record, config())
        self.assertEqual(held.exception.code, "classification_uncertain")

    def test_new_suppliers_foreign_documents_and_dates_before_the_books_hold_with_their_reasons(self):
        new = proposal(**{"voucher.party": {"ledger_guid": None, "new_supplier": True, "evidence": "No ledger has this GSTIN."}})
        cases = ((new, "supplier_missing"),
                 (proposal(**{"voucher.party.ledger_guid": None}), "supplier_unresolved"),
                 (proposal(**{"document.origin": "foreign"}), "identity_rule_unknown"),
                 (proposal(**{"document.date": "2026-03-31"}), "date_before_books"))
        for record, code in cases:
            with self.subTest(code=code), self.assertRaises(HoldReason) as held:
                vouchers.check(record, config())
            self.assertEqual(held.exception.code, code)
        self.assertEqual(vouchers.summary(new, config())["vendor"], "ACME CEMENT")
        self.assertIsNotNone(vouchers.check(new, config(), assume_new_supplier=True))

    def test_malformed_amounts_never_reach_a_plan(self):
        for record in (proposal(**{"voucher.lines.0.amount": 4000.001}), proposal(**{"voucher.lines.0.amount": -4000.00}),
                       proposal(**{"voucher.lines.0.side": "sideways"}), proposal(**{"document.date": "14/10/2026"})):
            with self.assertRaises(HoldReason):
                vouchers.check(copy.deepcopy(record), config())


if __name__ == "__main__":
    unittest.main()


def pattern(**changes):
    """A confirmed posting pattern for the fixture company."""
    from minkops_platform.accounts.posting_profiles import validate
    from minkops_platform.accounts.vouchers import Masters

    payload = {"company_guid": "company",
               "families": {"invoice": {"family": "purchase", "voucher_type_guid": "vt-purchase-gst"},
                            "credit_note": {"family": "debit_note", "voucher_type_guid": "vt-debit-note"}},
               "invoice_number": {"fields": ["REFERENCE", "NARRATION"]},
               "round_off": {"ledger_guid": guid("Round Off"), "max_cents": 50},
               "tds": {"deducted_at": "booking", "ledgers": [{"ledger_guid": guid("TDS Payable 194C"), "section": "194C", "rate": 1}]},
               "party_groups": ["Sundry Creditors"], "practice": [], "summary": ["Purchases: Purchase GST"], **changes}
    return validate(payload, Masters(company()), "company")


def with_pattern(payload):
    settings = config()
    settings["posting_profiles"] = {"company": {"id": "p", "version": 1, **payload}}
    return settings


class PostingPatternTest(unittest.TestCase):
    def test_a_parent_group_ancestry_change_invalidates_a_pattern(self):
        from minkops_platform.accounts.posting_profiles import holds, validate
        from minkops_platform.accounts.vouchers import Masters

        original = company()
        original['masters']['records'].append({'type': 'GROUP', 'data': {
            'NAME': 'Indirect Expenses', 'GUID': 'group-indirect', 'PARENT': 'Expenses'}})
        pinned = validate(pattern(), Masters(original), 'company')
        regrouped = copy.deepcopy(original)
        regrouped['masters']['records'][-1]['data']['PARENT'] = 'Current Liabilities'
        self.assertFalse(holds(pinned, Masters(regrouped)))

    def test_a_confirmed_pattern_allows_its_tds_and_sets_the_supplier_line(self):
        record = proposal()
        record["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "credit", 55.00))
        bill = vouchers.check(record, with_pattern(pattern()))
        self.assertEqual(bill.lines[0], {"ledger": "Acme Cement", "side": "credit", "amount_cents": 630000, "allocation": None})
        self.assertEqual(bill.native_plan("12345678-1234-5234-8234-123456789abc", "append", None)["duplicate"]["number_fields"],
                         ["REFERENCE", "NARRATION"])
        wrong_rate = proposal()
        wrong_rate["voucher"]["lines"].append(line("tds", "TDS Payable 194C", "credit", 110.00))
        with self.assertRaises(HoldReason):
            vouchers.check(wrong_rate, with_pattern(pattern()))

    def test_bills_outside_the_pattern_are_misses_not_silent_posts(self):
        journal = proposal(**{"voucher.family": "journal", "voucher.voucher_type_guid": "vt-journal"})
        rounded = proposal(**{"document.total": 6355.40})
        rounded["voucher"]["lines"].append(line("round_off", "Freight Inward", "debit", 0.40))
        rounded["voucher"]["lines"][6]["ledger_guid"] = guid("Purchase 5%")  # keep ledgers distinct
        too_big = proposal(**{"document.total": 6355.80})
        too_big["voucher"]["lines"].append(line("round_off", "Round Off", "debit", 0.80))
        for record, code in ((journal, "posting_profile_miss"), (too_big, "source_values_conflict")):
            with self.subTest(code=code), self.assertRaises(HoldReason) as held:
                vouchers.check(record, with_pattern(pattern()))
            self.assertEqual(held.exception.code, code)
        with self.assertRaises(HoldReason):
            vouchers.check(rounded, with_pattern(pattern()))
        outsider = with_pattern(pattern(party_groups=["Duties & Taxes"]))
        with self.assertRaises(HoldReason) as held:
            vouchers.check(proposal(), outsider)
        self.assertEqual(held.exception.code, "posting_profile_miss")

    def test_patterns_name_only_discovered_identities_and_survive_master_edits(self):
        from minkops_platform.accounts.posting_profiles import carry_forward, holds, validate
        from minkops_platform.accounts.vouchers import Masters

        for bad in ({"round_off": {"ledger_guid": "nowhere", "max_cents": 50}},
                    {"families": {"invoice": {"family": "purchase", "voucher_type_guid": "vt-journal"}, "credit_note": None}},
                    {"party_groups": ["Imaginary Group"]}, {"invoice_number": {"fields": []}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pattern(**bad)
        edited = company()
        for record in edited["masters"]["records"]:
            record["data"]["ALTERID"] = "99"
        self.assertTrue(holds(pattern(), Masters(edited)))
        regrouped = company()
        next(r for r in regrouped["masters"]["records"] if r["data"].get("NAME") == "Round Off")["data"]["PARENT"] = "Direct Expenses"
        self.assertFalse(holds(pattern(), Masters(regrouped)))
        sibling = company("Test (2027-28)", "next")
        carried = carry_forward(pattern(), Masters(sibling), "next")
        self.assertEqual(carried["round_off"]["ledger_guid"], "next-" + guid("Round Off"))
        self.assertEqual(carried["families"]["invoice"]["voucher_type_guid"], "vt-purchase-gst")
        missing = company("Test (2027-28)", "next")
        missing["masters"]["records"] = [r for r in missing["masters"]["records"] if r["data"].get("NAME") != "Round Off"]
        self.assertIsNone(carry_forward(pattern(), Masters(missing), "next"))
        self.assertTrue(validate(carried, Masters(sibling), "next"))
