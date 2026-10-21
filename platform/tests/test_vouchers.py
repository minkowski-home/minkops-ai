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
# What statement_routing.validated_plan resolves for one bank-charge payment.
RESOLVED = {
    "family": "payment", "lines": None, "company": "Test", "company_guid": "company", "port": 9000,
    "data": {"date": "2026-10-01", "amount_cents": -1770, "bank_ledger": "HDFC", "counter_ledger": "Bank Charges",
             "reference": "", "narration": "NEFT charges"},
    "allocation": {"category": "Sites", "centre": "Site 4", "category_guid": "cat", "centre_guid": "cc"},
    "voucher_type": {"NAME": "Payment", "GUID": "vt-payment"},
    "references": {"company_guid": "company", "ledgers": {k: LEDGERS[k] for k in ("HDFC", "Bank Charges")}},
}
STATEMENT = vouchers.statement_voucher(RESOLVED, remote_id=ID, identity="row")


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
        "bills": [{"ledger": ln["ledger"], "name": bill.get("name"), "type": bill["type"],
                   "amount_cents": bill["amount_cents"] if ln["side"] == "credit" else -bill["amount_cents"]}
                  for ln in plan["lines"] for bill in ln.get("bills") or []],
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


class StatementIdentityTest(unittest.TestCase):
    """Re-runs and the writer's tag check depend on these exact bytes."""

    def test_statement_row_identity_never_changes(self):
        from minkops_connectors.statement import row_identity

        row = {"reference": "  S123 456 ", "date": "2026-09-01", "amount_cents": -1_500_000, "balance_cents": 98_765_432}
        self.assertEqual(row_identity(row, 1), "5e5edb759d4aac94d0447fd5cf4aa37580f90bf018ba702747267474c5838862")
        # A repeated transaction keeps a distinct identity by its occurrence.
        self.assertEqual(row_identity(row, 2), "0182c6e6212e016d6847faf414c9c01e26169a22e2c31ddae1cb2c8f208f6b16")
        self.assertEqual(row_identity({**row, "reference": "s123 456"}, 1), row_identity(row, 1))

    def test_narration_tokens_include_the_tenant_and_never_change(self):
        identity = "5e5edb759d4aac94d0447fd5cf4aa37580f90bf018ba702747267474c5838862"
        tenant = "6f1e4c9a-2b7d-4e10-9c3a-5d8b7a6f0e21"
        key = "statement:company-guid:QA18 Bank Current"
        self.assertEqual(vouchers.narration_token(tenant, key, identity), "3bf1ae78-bdbb-56d5-96fe-1eeb4e74fd68")
        self.assertNotEqual(vouchers.narration_token("8a1f0d3e-0000-4000-8000-000000000001", key, identity),
                            vouchers.narration_token(tenant, key, identity))


class StatementVoucherTest(unittest.TestCase):
    def test_payment_keeps_its_tag_reference_and_allocation_and_lists_proven_siblings(self):
        sibling = "87654321-4321-5321-8321-cba987654321"
        plan = vouchers.statement_voucher(RESOLVED, remote_id=ID, identity="row", distinct=[sibling])
        self.assertEqual((plan["format_version"], plan["family"], plan["fence"]), (6, "payment", "strict"))
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
        self.assertEqual(plan["identity"], {"version": 2, "series": "statement", "rule": "statement_row", "hash": "row"})
        receipt = vouchers.statement_voucher({**RESOLVED, "family": "receipt", "allocation": None,
                                              "data": {**RESOLVED["data"], "amount_cents": 500, "reference": "UTR9"},
                                              "voucher_type": {"NAME": "Receipt", "GUID": "vt-receipt"}},
                                             remote_id=ID, identity="row")
        self.assertEqual((receipt["family"], receipt["header"]["reference"]), ("receipt", "UTR9"))
        self.assertEqual([(ln["ledger"], ln["side"]) for ln in receipt["lines"]], [("HDFC", "debit"), ("Bank Charges", "credit")])


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.bill = BILL
        self.statement = STATEMENT

    def test_a_bill_receipt_becomes_the_stored_observation_shape(self):
        view = vouchers.observed_bill(self.bill, "saved", observed(self.bill), identity=IDENTITY)
        self.assertEqual(view, {
            "master_id": "7", "guid": "a1b2c3d4-0000-4000-8000-000000000007", "date": "20261001",
            "invoice_number": "MOCK-1", "vendor": "Supplier", "voucher_type": "Purchase GST",
            "entries": [{"ledger": "CGST", "amount": -900}, {"ledger": "Purchases", "amount": -10000},
                        {"ledger": "SGST", "amount": -900}, {"ledger": "Supplier", "amount": 11800}],
            "bills": [], "fingerprint": "v5:" + "a" * 64,
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

    def test_a_correction_says_how_the_voucher_tally_already_has_differs(self):
        def reason(**overrides):
            current = observed(self.bill, **overrides)
            vouchers.observed_bill(self.bill, "correction", current, identity=IDENTITY)
            return vouchers.correction_reason(self.bill, current).removesuffix(
                " Review it there; Minkops did not add a second voucher.")

        swapped = [{"ledger": "Supplier", "amount_cents": 11800}, {"ledger": "Purchases", "amount_cents": -10000},
                   {"ledger": "Input CGST", "amount_cents": -900}, {"ledger": "Input SGST", "amount_cents": -900}]
        self.assertEqual(reason(lines=swapped),
                         "Tally's voucher for MOCK-1 posts to Input CGST, Input SGST instead of CGST, SGST.")
        larger = [{"ledger": "Supplier", "amount_cents": 12980}, {"ledger": "Purchases", "amount_cents": -11000},
                  {"ledger": "CGST", "amount_cents": -990}, {"ledger": "SGST", "amount_cents": -990}]
        self.assertEqual(reason(lines=larger, date="20261002"), "Tally's voucher for MOCK-1 is dated 2026-10-02; "
                                                                "comes to 129.80, not 118.00, with other amounts for "
                                                                "CGST, Purchases, SGST.")
        extra = [*observed(self.bill)["lines"], {"ledger": "Round Off", "amount_cents": -1}]
        self.assertEqual(reason(lines=extra), "Tally's voucher for MOCK-1 also posts to Round Off.")
        allocated = [{"ledger": "Purchases", "category": "Sites", "centre": "Site 4", "amount_cents": -10000}]
        self.assertEqual(reason(allocations=allocated), "Tally's voucher for MOCK-1 has other cost allocations.")

    def test_a_bill_by_bill_receipt_must_carry_the_approved_references(self):
        billed = {**BILL, "format_version": 6, "lines": [
            {**BILL["lines"][0], "bills": [{"name": "MOCK-1", "type": "New Ref", "amount_cents": 11800}]},
            *BILL["lines"][1:]]}
        view = vouchers.observed_bill(billed, "saved", observed(billed), identity=IDENTITY)
        self.assertEqual(view["bills"], [{"ledger": "Supplier", "name": "MOCK-1", "type": "New Ref", "amount_cents": 11800}])
        for bills in ([], [{"ledger": "Supplier", "name": "MOCK-2", "type": "New Ref", "amount_cents": 11800}]):
            with self.subTest(bills=bills), self.assertRaises(ValueError):
                vouchers.observed_bill(billed, "saved", observed(billed, bills=bills), identity=IDENTITY)

    def test_a_saved_correction_must_keep_the_voucher_it_replaced(self):
        plan = {**BILL, "operation": "update", "expected": {"guid": "a1b2c3d4-0000-4000-8000-000000000001", "fingerprint": "v5:x"}}
        with self.assertRaises(ValueError):
            vouchers.observed_bill(plan, "saved", observed(plan), identity=IDENTITY)
        kept = observed(plan, guid="a1b2c3d4-0000-4000-8000-000000000001", voucher_type="Purchase")
        self.assertEqual(vouchers.observed_bill(plan, "saved", kept, identity=IDENTITY)["voucher_type"], "Purchase")

    def test_a_statement_receipt_must_carry_its_tag_lines_and_allocation(self):
        view = vouchers.observed_statement(self.statement, observed(self.statement))
        self.assertEqual(view["allocations"], [{"ledger": "Bank Charges", "category": "Sites", "centre": "Site 4", "amount_cents": -1770}])
        self.assertEqual(view["entries"], [{"ledger": "Bank Charges", "amount": -1770}, {"ledger": "HDFC", "amount": 1770}])
        self.assertEqual(view["tag"], ID)
        for current in (observed(self.statement, tag=None), observed(self.statement, allocations=[]),
                        observed(self.statement, voucher_type="Receipt"), observed(self.statement, date="20261002")):
            with self.subTest(current=current), self.assertRaises(ValueError):
                vouchers.observed_statement(self.statement, current)


if __name__ == "__main__":
    unittest.main()
