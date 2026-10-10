"""Attention completion is evidence-based, never inferred from a UI visit."""
import unittest
from minkops_platform.attention import resolved, label


class AttentionEvidenceTests(unittest.TestCase):
    def test_review_requires_edit_and_valid_observation(self):
        item = {"kind": "review", "target": {"baseline": {"guid": "v", "fingerprint": "old"}}}
        self.assertFalse(resolved(item, {"current": {"guid": "v", "fingerprint": "old"}, "valid": True}))
        self.assertFalse(resolved(item, {"current": {"guid": "another", "fingerprint": "new"}, "valid": True}))
        self.assertFalse(resolved(item, {"current": {"guid": "v", "fingerprint": "new"}, "valid": False}))
        self.assertTrue(resolved(item, {"current": {"guid": "v", "fingerprint": "new"}, "valid": True}))

    def test_missing_supplier_needs_exact_native_master(self):
        item = {"kind": "supplier", "target": {"vendor": "Supplier"}}
        self.assertFalse(resolved(item, {"ledgers": ["supplier"], "valid": True}))
        self.assertTrue(resolved(item, {"ledgers": ["Supplier"], "valid": True}))

    def test_unknown_unrefreshable_events_stay_pending(self):
        self.assertFalse(resolved({"kind": "manual", "target": {}}, {"valid": True}))
        self.assertEqual(label("Bill company conflicts with the locked company."), "Company mismatch")
        self.assertEqual(label("A selected ledger changed since discovery."), "Source changed")
