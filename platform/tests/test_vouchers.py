"""Plan protocol 5: one voucher contract whose receipts verify exactly."""

import unittest
from datetime import date

from minkops_platform.accounts import vouchers

ID = "12345678-1234-5234-8234-123456789abc"
LEDGERS = {name: {"GUID": f"{name}-guid", "PARENT": "Group", "ALTERID": "12"}
           for name in ("Supplier", "Purchases", "CGST", "SGST", "Tax", "HDFC", "Bank Charges")}

IDENTITY = vouchers.document_identity("Supplier", "MOCK-1", date(2026, 10, 1))
BILL = {
    "format_version": 5, "operation": "append", "company": "Test", "port": 9000, "remote_id": ID,
    "family": "purchase", "fence": "retry_after_read", "company_guid": "company",
    "voucher_type": {"NAME": "Purchase GST", "GUID": "vt"},
    "header": {"date": "2026-10-01", "reference": "MOCK-1", "party_ledger": "Supplier",
               "narration": "Minkops reviewed bill MOCK-1", "tag": None},
    "lines": [{"ledger": "Supplier", "side": "credit", "amount_cents": 11800, "allocation": None},
              {"ledger": "Purchases", "side": "debit", "amount_cents": 10000, "allocation": None},
              {"ledger": "CGST", "side": "debit", "amount_cents": 900, "allocation": None},
              {"ledger": "SGST", "side": "debit", "amount_cents": 900, "allocation": None}],
    "references": {"company_guid": "company", "ledgers": {k: LEDGERS[k] for k in ("Supplier", "Purchases", "CGST", "SGST")}},
    "duplicate": {"strategy": "document", "families": ["purchase", "journal"], "party_ledger": "Supplier",
                  "number": "MOCK-1", "number_fields": ["REFERENCE"], "window": {"from": "2026-04-01", "to": "2027-03-31"}},
    "expected": None,
    "identity": {"version": 2, "series": "invoice", "rule": "in_invoice_year", "hash": IDENTITY},
}
STATEMENT = {
    "format_version": 4, "operation": "append", "company": "Test", "company_guid": "company", "port": 9000,
    "remote_id": ID, "destination_key": "statement:company:HDFC",
    "voucher_type": {"NAME": "Payment", "GUID": "vt-payment"},
    "allocation": {"category": "Sites", "centre": "Site 4", "category_guid": "cat", "centre_guid": "cc"},
    "data": {"date": "2026-10-01", "amount_cents": -1770, "bank_ledger": "HDFC", "counter_ledger": "Bank Charges",
             "reference": "", "narration": "NEFT charges"},
    "references": {"company_guid": "company", "ledgers": {k: LEDGERS[k] for k in ("HDFC", "Bank Charges")}},
}


def observed(plan, **overrides):
    """The v5 voucher view a companion reports for exactly this v5 plan."""
    signed = [{"ledger": ln["ledger"], "amount_cents": ln["amount_cents"] if ln["side"] == "credit" else -ln["amount_cents"]}
              for ln in plan["lines"]]
    current = {
        "guid": "a1b2c3d4-0000-4000-8000-000000000007", "master_id": "7", "date": plan["header"]["date"].replace("-", ""),
        "voucher_type": plan["voucher_type"]["NAME"], "family": plan["family"],
        "reference": plan["header"]["reference"] or "", "number": "", "narration": plan["header"]["narration"],
        "party_ledger": plan["header"]["party_ledger"] or "",
        "tag": plan["remote_id"] if plan["header"]["tag"] else None,
        "lines": sorted(signed, key=lambda e: (e["ledger"], e["amount_cents"])),
        "allocations": [{"ledger": ln["ledger"], "category": ln["allocation"]["category"], "centre": ln["allocation"]["centre"],
                         "amount_cents": next(e["amount_cents"] for e in signed if e["ledger"] == ln["ledger"])}
                        for ln in plan["lines"] if ln["allocation"]],
        "fingerprint": "v5:" + "a" * 64,
    }
    current.update(overrides)
    return current


class InvoiceYearTest(unittest.TestCase):
    def test_indian_invoice_year_turns_on_the_first_of_april(self):
        self.assertEqual(vouchers.invoice_year(date(2027, 3, 31)), 2026)
        self.assertEqual(vouchers.invoice_year(date(2027, 4, 1)), 2027)
        self.assertEqual(vouchers.invoice_window(date(2027, 3, 31)), {"from": "2026-04-01", "to": "2027-03-31"})

    def test_document_identity_never_changes_for_vouchers_already_in_tally(self):
        # Saved vouchers, remote IDs and pending reservations all derive from these bytes.
        self.assertEqual(vouchers.document_identity("  Supplier ", "mock-1", date(2026, 10, 1)),
                         "e49806dbc9499a06a79a03e636fd212c410a04e6895c81dd447872e06133b471")
        self.assertEqual(vouchers.document_identity("Supplier", "MOCK-1", date(2026, 10, 1), series="credit_note"),
                         "1678d9ba34152e0ffb930fefbf9d2d03a4a11c0913de6e28d5b48273606fb8bc")
        march = vouchers.document_identity("Supplier", "MOCK-1", date(2027, 3, 31))
        self.assertNotEqual(march, vouchers.document_identity("Supplier", "MOCK-1", date(2027, 4, 1)))
        self.assertNotEqual(vouchers.document_identity("Supplier", "MOCK-1", date(2026, 10, 1), series="credit_note"),
                            vouchers.document_identity("Supplier", "MOCK-1", date(2026, 10, 1)))


class UpgradeTest(unittest.TestCase):
    def test_payment_keeps_its_tag_reference_and_allocation_and_lists_proven_siblings(self):
        sibling = "87654321-4321-5321-8321-cba987654321"
        plan = vouchers.upgrade(STATEMENT, identity="row", distinct=[sibling])
        self.assertEqual((plan["family"], plan["fence"]), ("payment", "strict"))
        self.assertEqual(plan["lines"], [
            {"ledger": "HDFC", "side": "credit", "amount_cents": 1770, "allocation": None},
            {"ledger": "Bank Charges", "side": "debit", "amount_cents": 1770,
             "allocation": {"category": "Sites", "category_guid": "cat", "centre": "Site 4", "centre_guid": "cc"}},
        ])
        self.assertEqual(plan["header"], {"date": "2026-10-01", "reference": ID, "party_ledger": None,
                                          "narration": "NEFT charges", "tag": "statement"})
        self.assertEqual(plan["duplicate"], {"strategy": "tag", "window": {"from": "2026-10-01", "to": "2026-10-01"},
                                             "match": {"ledger": "HDFC", "side": "credit", "amount_cents": 1770},
                                             "distinct": [sibling]})
        receipt = vouchers.upgrade({**STATEMENT, "data": {**STATEMENT["data"], "amount_cents": 500, "reference": "UTR9"},
                                    "voucher_type": {"NAME": "Receipt", "GUID": "vt-receipt"}, "allocation": None}, identity="row")
        self.assertEqual((receipt["family"], receipt["header"]["reference"]), ("receipt", "UTR9"))
        self.assertEqual([(ln["ledger"], ln["side"]) for ln in receipt["lines"]], [("HDFC", "debit"), ("Bank Charges", "credit")])

    def test_v5_plans_and_unknown_formats_are_not_rewritten(self):
        self.assertIs(vouchers.upgrade(BILL, identity=IDENTITY), BILL)
        self.assertIsNone(vouchers.upgrade({**STATEMENT, "format_version": 7}, identity="row"))

    def test_legacy_statement_upgrade_compares_siblings_in_both_plan_formats(self):
        from minkops_platform.desktop import _native_plan

        same = vouchers.upgrade({**STATEMENT, "remote_id": "same-v5"}, identity="same")
        other = vouchers.upgrade({**STATEMENT, "remote_id": "other-v5",
            "data": {**STATEMENT["data"], "amount_cents": 1770}}, identity="other")
        for plan in (same, other):
            plan["destination_key"] = STATEMENT["destination_key"]
        run = {"result": {"records": [{"plan": p} for p in (STATEMENT, same, other)]}}
        upgraded = _native_plan(run, {"plan": STATEMENT, "identity": "legacy"}, 5)
        self.assertEqual(upgraded["duplicate"]["distinct"], ["same-v5"])


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.bill = BILL
        self.statement = vouchers.upgrade(STATEMENT, identity="row")

    def test_a_bill_receipt_becomes_the_stored_observation_shape(self):
        view = vouchers.observed_bill(self.bill, "saved", observed(self.bill), identity=IDENTITY)
        self.assertEqual(view, {
            "master_id": "7", "guid": "a1b2c3d4-0000-4000-8000-000000000007", "date": "20261001",
            "invoice_number": "MOCK-1", "vendor": "Supplier", "voucher_type": "Purchase GST",
            "entries": [{"ledger": "CGST", "amount": -900}, {"ledger": "Purchases", "amount": -10000},
                        {"ledger": "SGST", "amount": -900}, {"ledger": "Supplier", "amount": 11800}],
            "fingerprint": "v5:" + "a" * 64,
        })

    def test_tampered_bill_receipts_are_rejected(self):
        tampered = [
            observed(self.bill, lines=[{"ledger": "Supplier", "amount_cents": 11800}, {"ledger": "Purchases", "amount_cents": -11800}]),
            observed(self.bill, date="20261002"),
            observed(self.bill, party_ledger="Other Supplier"),
            observed(self.bill, reference="MOCK-2"),
            observed(self.bill, voucher_type="Purchase"),
            observed(self.bill, allocations=[{"ledger": "Purchases", "category": "Sites", "centre": "Site 4", "amount_cents": -10000}]),
            observed(self.bill, lines="not lines"),
            {**observed(self.bill), "extra": True},
        ]
        for current in tampered:
            with self.subTest(current=current), self.assertRaises(ValueError):
                vouchers.observed_bill(self.bill, "saved", current, identity=IDENTITY)
        # A correction reports a different existing version; only its identity must match.
        different = observed(self.bill, lines=[{"ledger": "Supplier", "amount_cents": 11800}, {"ledger": "Purchases", "amount_cents": -11800}])
        self.assertEqual(vouchers.observed_bill(self.bill, "correction", different, identity=IDENTITY)["guid"], different["guid"])
        with self.assertRaises(ValueError):
            vouchers.observed_bill(self.bill, "correction", observed(self.bill, reference="MOCK-2"), identity=IDENTITY)

    def test_a_saved_correction_must_keep_the_voucher_it_replaced(self):
        plan = {**BILL, "operation": "update", "expected": {"guid": "a1b2c3d4-0000-4000-8000-000000000001", "fingerprint": "v5:x"}}
        with self.assertRaises(ValueError):
            vouchers.observed_bill(plan, "saved", observed(plan), identity=IDENTITY)
        kept = observed(plan, guid="a1b2c3d4-0000-4000-8000-000000000001", voucher_type="Purchase")
        self.assertEqual(vouchers.observed_bill(plan, "saved", kept, identity=IDENTITY)["voucher_type"], "Purchase")

    def test_a_statement_receipt_must_carry_its_tag_lines_and_allocation(self):
        view = vouchers.observed_statement(self.statement, STATEMENT, observed(self.statement))
        self.assertEqual(view["allocation"], STATEMENT["allocation"])
        self.assertEqual(view["entries"], [{"ledger": "Bank Charges", "amount": -1770}, {"ledger": "HDFC", "amount": 1770}])
        self.assertEqual(view["tag"], ID)
        for current in (observed(self.statement, tag=None), observed(self.statement, allocations=[]),
                        observed(self.statement, voucher_type="Receipt"), observed(self.statement, date="20261002")):
            with self.subTest(current=current), self.assertRaises(ValueError):
                vouchers.observed_statement(self.statement, STATEMENT, current)


    def test_a_refresh_observation_must_name_the_same_document(self):
        target = {"vendor": "Supplier", "invoice_number": "MOCK-1"}
        view = vouchers.observed_document(observed(self.bill), target)
        self.assertEqual((view["invoice_number"], view["vendor"], view["fingerprint"][:3]), ("MOCK-1", "Supplier", "v5:"))
        self.assertIsNone(vouchers.observed_document(observed(self.bill, reference="MOCK-2"), target))
        self.assertIsNone(vouchers.observed_document(observed(self.bill, party_ledger="Other"), target))
        self.assertIsNone(vouchers.observed_document({"lines": []}, target))


class AttentionReaderTest(unittest.TestCase):
    def test_protocol_five_refreshes_read_the_invoice_window_unless_an_older_reader_saved_the_baseline(self):
        from minkops_platform.attention import native_target
        target = {"tool": "tally", "date": "2027-03-31", "vendor": "Supplier", "invoice_number": "MOCK-1", "baseline": None}
        self.assertEqual(native_target(target, 5)["document"],
                         {"window": {"from": "2026-04-01", "to": "2027-03-31"}, "number_fields": ["REFERENCE"],
                          "families": ["purchase", "journal"]})
        self.assertNotIn("document", native_target(target, 4))
        self.assertNotIn("document", native_target({**target, "baseline": {"fingerprint": "a" * 64}}, 5))
        self.assertIn("document", native_target({**target, "baseline": {"fingerprint": "v5:" + "a" * 64}}, 5))
        self.assertNotIn("document", native_target({**target, "date": None}, 5))

    def test_a_reader_change_is_never_mistaken_for_an_edit_in_tally(self):
        from minkops_platform.attention import resolved
        baseline = {"guid": "g", "fingerprint": "a" * 64}
        item = {"kind": "review", "target": {"baseline": baseline}}
        self.assertFalse(resolved(item, {"valid": True, "current": {"guid": "g", "fingerprint": "v5:" + "b" * 64}}))
        self.assertTrue(resolved(item, {"valid": True, "current": {"guid": "g", "fingerprint": "b" * 64}}))
        v5 = {"kind": "review", "target": {"baseline": {"guid": "g", "fingerprint": "v5:" + "a" * 64}}}
        self.assertTrue(resolved(v5, {"valid": True, "current": {"guid": "g", "fingerprint": "v5:" + "b" * 64}}))


if __name__ == "__main__":
    unittest.main()
