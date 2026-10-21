"""A missing supplier holds its own bill without blocking valid siblings."""

import unittest

from minkops_platform.accounts.bills import capture_tally_findings


class BillIdentityTests(unittest.TestCase):
    def test_missing_supplier_is_held_without_blocking_valid_siblings(self):
        from test_bill_vouchers import config, proposal

        unknown = proposal(**{"source_file_id": "unknown", "document.supplier_name": "Unknown Supplier",
                              "voucher.party": {"ledger_guid": None, "new_supplier": True, "evidence": "No ledger has this GSTIN."}})
        result = {"records": [unknown, proposal(**{"source_file_id": "known"})], "findings": []}
        settings = config()
        capture_tally_findings(result, settings)
        self.assertEqual(result["records"][0]["decision"], "hold")
        self.assertEqual(result["unresolved"][0]["code"], "supplier_missing")
        self.assertIn("Unknown Supplier", result["unresolved"][0]["reason"])
        self.assertNotIn("decision", result["records"][1])
        capture_tally_findings(result, settings)
        self.assertEqual(len(result["unresolved"]), 1)
