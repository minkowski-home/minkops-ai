"""Business invariants for the disposable live Tally rehearsal package."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_tally_demo import build_company, money, validate_company  # noqa: E402


class TallyDemoTests(unittest.TestCase):
    def setUp(self):
        self.company = build_company(
            {
                "company": "Test & Company",
                "company_guid": "test-company-guid",
                "identity": {"BOOKSFROM": "20260401", "STATENAME": "Rajasthan"},
            },
            1,
        )

    def test_all_document_and_voucher_dates_work_in_educational_tally(self):
        for record in self.company["bills"] + self.company["vouchers"]:
            self.assertIn(int(record["date"][-2:]), (1, 2, 31))

    def test_native_unit_symbols_are_compact_and_stock_items_use_them(self):
        units = {m["name"] for m in self.company["masters"] if m["type"] == "UNIT"}
        self.assertTrue(all(not any(c.isspace() for c in name) for name in units))
        self.assertTrue(all(name.isalpha() for name in units))
        for item in (m for m in self.company["masters"] if m["type"] == "STOCKITEM"):
            self.assertIn(item["unit"], units)

    def test_exact_balancing_and_independent_line_arithmetic(self):
        for voucher in self.company["vouchers"]:
            self.assertEqual(sum(Decimal(e["amount"]) for e in voucher["entries"]), 0)
        for bill in self.company["bills"]:
            self.assertGreaterEqual(len(bill["lines"]), 4)
            self.assertEqual(
                sum(Decimal(line["net"]) for line in bill["lines"]), Decimal(bill["subtotal"])
            )
            self.assertEqual(
                money(
                    Decimal(bill["subtotal"]) + Decimal(bill["tax"]) + Decimal(bill["round_off"])
                ),
                bill["total"],
            )

    def test_unseeded_bills_and_absent_supplier_are_deliberate(self):
        seeded = {v["reference"] for v in self.company["vouchers"]}
        for bill in self.company["bills"]:
            self.assertEqual(
                bill["invoice_number"] in seeded,
                bill["case"] in ("existing_duplicate", "conflicting_version"),
            )
        missing = next(b for b in self.company["bills"] if b["case"] == "missing_supplier")
        self.assertNotIn(missing["supplier"], {m["name"] for m in self.company["masters"]})

    def test_guid_scoping_and_same_bill_scan_copy(self):
        other = build_company(
            {"company": "Other", "company_guid": "other", "identity": {"BOOKSFROM": "20260401"}}, 2
        )
        self.assertFalse(
            {v["guid"] for v in self.company["vouchers"]} & {v["guid"] for v in other["vouchers"]}
        )
        original, copy = self.company["bills"][0], self.company["bills"][-1]
        self.assertEqual(copy["duplicate_of"], original["id"])
        self.assertEqual(copy["invoice_number"], original["invoice_number"])
        self.assertEqual(copy["total"], original["total"])

    def test_rejects_corrupt_plan_before_any_live_import(self):
        self.company["vouchers"][0]["entries"][0]["amount"] = "0.01"
        with self.assertRaisesRegex(ValueError, "Unbalanced"):
            validate_company(self.company)

    def test_before_books_fixture_preserves_real_date(self):
        bill = next(b for b in self.company["bills"] if b["case"] == "before_books")
        self.assertEqual(bill["date"], "2026-03-31")
        self.assertEqual(bill["expected"], "attention")

    def test_scorer_accepts_required_holds_and_rejects_flattened_saves(self):
        from bill_entry_fixtures import grade

        def record(status, *codes):
            return {"status": status, "hold_codes": list(codes), "review_reasons": [], "proposal": None,
                    "current": None, "company_guid": None}

        for case, code in (("before_books", "date_before_books"), ("inventory_required", "unsupported_structure")):
            bill = next(b for b in self.company["bills"] if b["case"] == case)
            with self.subTest(case=case):
                self.assertEqual(grade(bill, [record("held", code)])[0], "correct")
                self.assertEqual(grade(bill, [record("saved")])[0], "missed_exception!")
                self.assertEqual(grade(bill, [record("held", "extraction_failed")])[0], "wrong_reason")

    def test_scorer_compares_the_proposed_voucher_with_its_label(self):
        import json
        import tempfile

        from bill_entry_fixtures import compare, grade, load_expected

        bill = {**self.company["bills"][0], "sha256": "sample-hash"}
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence"
            evidence.mkdir()
            (evidence / "expected-bills.json").write_text(json.dumps([bill]))
            expected = load_expected([directory])["sample-hash"]
        lines = [{"ledger": bill["purchase_ledger"], "side": "debit", "amount": bill["subtotal"]},
                 *({"ledger": t["ledger"], "side": "debit", "amount": t["amount"]} for t in bill["tax_allocations"])]
        record = {"status": "proposed", "hold_codes": [], "review_reasons": [], "current": None,
                  "company_guid": bill["company_guid"], "proposal": {"preview": {
                      "number": bill["invoice_number"], "date": bill["date"], "party": bill["supplier"],
                      "total": bill["total"], "lines": [{"ledger": bill["supplier"], "side": "credit",
                                                         "amount": bill["total"]}, *lines]}}}
        self.assertEqual(compare(expected, record), [])
        self.assertEqual(grade(expected, [record])[0], "correct_ready")
        record["proposal"]["preview"]["lines"][1]["ledger"] = "Another Purchase"
        self.assertEqual(grade(expected, [record])[0], "wrong_proposal!")


if __name__ == "__main__":
    unittest.main()
