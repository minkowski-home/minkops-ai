"""Business identity survives retries, imports and extraction order changes."""

import unittest

from minkops_platform.accounts.bills import business_identity, classify_excel
from minkops_platform.accounts.checks import populate_entry_ids


class BillIdentityTests(unittest.TestCase):
    def test_identity_uses_supplier_invoice_and_financial_year(self):
        a = {"vendor": " ACME ", "invoice_number": "Inv-01", "date": "2026-10-01"}
        b = {**a, "vendor": "acme", "date": "2026-11-01", "total": 999}
        self.assertEqual(business_identity(a), business_identity(b))
        self.assertNotEqual(business_identity(a), business_identity({**a, "date": "2027-10-01"}))
        self.assertNotEqual(business_identity(a), business_identity({**a, "vendor": "Other"}))

    def test_incomplete_identity_cannot_be_written(self):
        with self.assertRaises(ValueError):
            business_identity({"vendor": "Acme", "invoice_number": "", "date": "2026-10-01"})

    def test_excel_classifies_exact_duplicate_correction_and_ambiguous_keys(self):
        mapping = {
            "key_columns": ["Invoice", "Vendor"],
            "columns": [
                {"name": "Invoice", "concept": "invoice_number"},
                {"name": "Vendor", "concept": "vendor"},
                {"name": "Amount", "concept": "total"},
            ],
        }
        data = {"Invoice": "A-1", "Vendor": "Acme", "Amount": 12}
        rows = [{"data": data}]
        self.assertEqual(classify_excel(data, mapping, rows), "duplicate")
        self.assertEqual(classify_excel({**data, "Amount": 12.0}, mapping, rows), "duplicate")
        self.assertEqual(classify_excel({**data, "Amount": 24}, mapping, rows), "correction")
        self.assertEqual(classify_excel(data, mapping, rows * 2), "ambiguous")
        self.assertEqual(classify_excel({**data, "Invoice": "A-2"}, mapping, rows), "new")

    def test_generated_ids_survive_new_uploads_and_follow_reviewed_identity(self):
        mapping = {
            "file_id": "register",
            "sheet": "Bills",
            "table": None,
            "role": "destination",
            "key_columns": ["Vendor", "Invoice"],
            "columns": [
                {"name": "Invoice", "concept": "invoice_number", "type": "string"},
                {"name": "Vendor", "concept": "vendor", "type": "string"},
                {"name": "Date", "concept": "date", "type": "string"},
                {"name": "Row", "concept": "entry_id", "type": "string"},
            ],
        }
        record = {
            "destination_file_id": "register",
            "sheet": "Bills",
            "data": {"Invoice": "A-1", "Vendor": "Acme", "Date": "2026-10-01"},
        }
        result = {"records": [record]}
        populate_entry_ids(result, {"sheets": [mapping]}, "first-run")
        first_id = record["data"]["Row"]
        record["source_file_id"] = "different-upload"
        populate_entry_ids(result, {"sheets": [mapping]}, "another-run")
        self.assertEqual(first_id, record["data"]["Row"])
        record["data"]["Invoice"] = "A-2"
        populate_entry_ids(result, {"sheets": [mapping]}, "another-run")
        self.assertNotEqual(first_id, record["data"]["Row"])
