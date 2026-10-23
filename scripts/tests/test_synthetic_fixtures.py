"""The committed synthetic look-alikes keep the structure the rebuild depends on.

These read the fixtures only; regenerating them needs the dev dependency group.
When the private store is present, the real PR Infra files are checked against
the same structural facts without printing any client identifier.
"""

import json
import os
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

from minkops_connectors.statement import apply_layout, read_tables
from minkops_platform.accounts.supplier_gst import gstin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from pr_infra_acceptance import icici_layout, prove_statement  # noqa: E402

SYNTHETIC = ROOT / "packages/fixtures/synthetic"
STATEMENT = SYNTHETIC / "statements/icici-detailed-statement-sep-2026.xlsx"
PRIVATE = Path(os.getenv("MINKOPS_PRIVATE_FIXTURES", Path.home() / "minkops-private/fixtures")) / "pr-infra"
FAMILIES = ("NEFT-RETURN", "INF/NEFT", "MMT/IMPS", "INF/INFT", "RTGS", "BIL/ONL", "UPI")


def family(narration):
    text = narration.upper()
    return next((name for name in FAMILIES if name in text), "other")


def transactions(path):
    (sheet, table, formulas), = read_tables(path.read_bytes(), ".xlsx")
    rows, proof = apply_layout(table, icici_layout(), 16, sheet=sheet, formulas=formulas)
    return table, rows, proof


def image_only(path):
    content = path.read_bytes()
    return {"pages": len(re.findall(rb"/Type\s*/Page\b", content)), "fonts": content.count(b"/Font"),
            "jpeg_pages": content.count(b"/DCTDecode")}


class SyntheticStatementTest(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads(STATEMENT.with_suffix(".expected.json").read_text())
        self.table, self.rows, self.proof = transactions(STATEMENT)

    def test_it_proves_through_the_declared_bank_layout_including_footer_controls(self):
        summary = prove_statement(STATEMENT)["sheets"][0]
        self.assertEqual((summary["rows"], summary["payments"], summary["receipts"]), (1232, 1203, 29))
        self.assertTrue(self.proof["amounts"] and self.proof["date_order"] and self.proof["summary"])
        self.assertEqual(self.rows[-1]["balance_cents"], self.expected["closing_cents"])

    def test_values_are_bank_text_in_indian_grouping_and_three_date_formats(self):
        first = self.table[17]
        self.assertRegex(first[2], r"^\d{2}/[A-Z][a-z]{2}/\d{4}$")
        self.assertRegex(first[4], r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} [AP]M$")
        balances = [row[9] for row in self.table[17:17 + 1232]]
        self.assertTrue(all(isinstance(b, str) for b in balances))
        self.assertTrue(any(re.fullmatch(r"\d{1,2},\d{2},\d{2},\d{3}\.\d{2}", b) for b in balances))
        self.assertTrue(all(not (row[5] or "").strip() for row in self.table[17:17 + 1232]))

    def test_the_type_filter_label_does_not_filter_and_metadata_names_the_account(self):
        labels = {row[0]: row[1] for row in self.table[:16] if row and row[0]}
        self.assertEqual(labels["Transaction type:"], "DR")
        self.assertTrue(any(r["amount_cents"] > 0 for r in self.rows))
        self.assertTrue(re.fullmatch(r"\d{12}", labels["A/C No:"]))
        self.assertIn("IFSC Code:", [row[5] for row in self.table[:16] if len(row) > 5])

    def test_narration_families_payee_spread_and_returns_match_the_real_month(self):
        counts = Counter(family(r["narration"]) for r in self.rows)
        self.assertEqual(counts, Counter({"INF/NEFT": 700, "UPI": 208, "RTGS": 130, "MMT/IMPS": 106,
                                          "INF/INFT": 55, "other": 19, "NEFT-RETURN": 8, "BIL/ONL": 6}))
        self.assertEqual(self.expected["distinct_payees"], 881)
        neft = {}
        for row in self.rows:
            if family(row["narration"]) == "INF/NEFT":
                neft[row["narration"].split("/")[2]] = row
        for row in self.rows:
            if family(row["narration"]) == "NEFT-RETURN":
                original = neft[row["narration"].split("-")[2]]
                self.assertEqual((original["date"], original["amount_cents"]), (row["date"], -row["amount_cents"]))

    def test_a_repeated_bank_transaction_id_keeps_distinct_row_identities(self):
        repeated = [tran for tran, n in Counter(r["reference"] for r in self.rows).items() if n > 1]
        self.assertEqual(len(repeated), 1)
        identities = {r["identity"] for r in self.rows if r["reference"] == repeated[0]}
        self.assertEqual(len(identities), 2)
        self.assertEqual(len({r["identity"] for r in self.rows}), 1232)


class SyntheticBillsTest(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads((SYNTHETIC / "bills/expected.json").read_text())

    def test_bills_are_two_page_image_only_scans(self):
        for bill in self.expected:
            self.assertEqual(image_only(SYNTHETIC / "bills" / bill["file"]), {"pages": 2, "fonts": 0, "jpeg_pages": 2})

    def test_answers_balance_and_name_valid_registrations_in_other_states(self):
        for bill in self.expected:
            taxable = sum(float(line["taxable"]) for line in bill["lines"])
            self.assertAlmostEqual(taxable, float(bill["taxable"]), places=2)
            self.assertAlmostEqual(float(bill["taxable"]) + float(bill["tax"]) + float(bill["round_off"]),
                                   float(bill["total"]), places=2)
            for number in (bill["supplier_gstin"], bill["buyer_gstin"], bill["bank_registration_gstin"]):
                self.assertEqual(gstin(number), number)
            self.assertNotEqual(bill["buyer_gstin"][:2], bill["bank_registration_gstin"][:2])
            self.assertEqual(bill["qr"]["DocNo"], bill["invoice_number"])
        self.assertEqual({b["case"] for b in self.expected},
                         {"tax_inclusive_amount_column", "goods_and_services_lines"})
        self.assertEqual({b["tax_mode"] for b in self.expected}, {"intra", "inter"})

    def test_file_names_follow_the_receipt_register_pattern(self):
        for bill in self.expected:
            self.assertTrue(bill["file"].startswith(bill["dmr"] + " "))
            self.assertRegex(bill["file"], r"\d{1,2}\.\d{1,2}\.\d{2}\.pdf$")


@unittest.skipUnless(PRIVATE.is_dir(), "Private PR Infra fixtures are not on this machine.")
class PrivateFixturesTest(unittest.TestCase):
    """Structure only: the assertions mirror docs/rebuild/evidence.md aggregates."""

    def test_the_real_statement_proves_and_keeps_its_measured_structure(self):
        (statement,) = (PRIVATE / "statements").glob("*.xlsx")
        _, rows, proof = transactions(statement)
        self.assertTrue(proof["amounts"] and proof["date_order"] and proof["summary"])
        self.assertEqual((len(rows), sum(r["amount_cents"] < 0 for r in rows)), (1232, 1203))
        returns = [r for r in rows if family(r["narration"]) == "NEFT-RETURN"]
        self.assertEqual(len(returns), 8)

    def test_the_real_bills_are_image_only_two_page_scans(self):
        bills = sorted((PRIVATE / "bills").glob("*.pdf"))
        self.assertGreaterEqual(len(bills), 2)
        for path in bills:
            self.assertEqual(image_only(path)["fonts"], 0)
            self.assertEqual(image_only(path)["pages"], 2)


if __name__ == "__main__":
    unittest.main()
