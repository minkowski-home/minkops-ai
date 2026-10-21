"""Contract and policy checks without agent calls or database requirements."""

import json
import unittest
from pathlib import Path

from jsonschema import ValidationError

from minkops_platform.workflows import (
    load_definition,
    resolve_run_config,
)

ROOT = Path(__file__).resolve().parents[2]


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.defaults = json.loads((ROOT / "db/fixtures/mock_workflows.json").read_text())
        self.examples = json.loads((ROOT / "db/fixtures/mock_workflow_runs.json").read_text())

    def definition(self, key):
        return load_definition(ROOT / "employees/accounts-desk/workflows" / key)

    def resolve(self, key, values=None, **policy):
        return resolve_run_config(
            self.definition(key),
            self.defaults[key],
            self.examples[key] if values is None else values,
            allowed_source_ids=policy.pop("allowed_source_ids", {"mock-reference", "mock-bills"}),
            allowed_destination_ids=policy.pop("allowed_destination_ids", {"mock-excel-draft"}),
            **policy,
        )

    def test_definitions_and_mock_run_contracts(self):
        for key in self.defaults:
            self.assertEqual(self.definition(key).metadata["owner"], "accounts-desk")
            self.resolve(key)

    def test_bill_bundle_reuses_confirmed_practice_without_skipping_current_bill_proof(self):
        """Guidance is pinned with the run; the live benchmark tests its effect."""
        snapshot = self.definition("bill-entry").execution_snapshot
        procedure = snapshot["files"][snapshot["execution"]["instructions"]]
        skill = snapshot["files"]["SKILL.md"]
        for text in (procedure, skill):
            self.assertIn("config.posting_profiles[company_guid]", text)
            self.assertIn("uncovered or contradictory", text)
            self.assertIn("current bill", text)
        self.assertIn("inventory allocations", procedure)
        self.assertIn("classification_uncertain", procedure)
        self.assertIn("same supplier, invoice reference and financial year", procedure)
        self.assertEqual(snapshot["execution"], {
            "environment": "openai_hosted", "model": "gpt-6-luna",
            "python_packages": ["pymupdf"], "instructions": "execution-instructions.md",
            "resources": [], "result_path": "/workspace/outputs/result.json"})

    def test_run_override_does_not_change_defaults_or_other_runs(self):
        selections = {**self.examples["source-discovery"], "max_files": 3}
        resolved = self.resolve("source-discovery", selections)
        self.assertEqual(resolved["max_files"], 3)
        resolved["source_ids"].append("changed")
        self.assertEqual(selections["source_ids"], ["mock-reference"])
        self.assertEqual(self.resolve("source-discovery")["max_files"], 100)

    def test_run_cannot_authorize_its_own_sources_or_destinations(self):
        with self.assertRaises(ValueError):
            self.resolve("source-discovery", allowed_source_ids=set())
        with self.assertRaises(ValueError):
            self.resolve("bill-entry", allowed_destination_ids=set())

    def test_review_requirement_cannot_be_overridden(self):
        with self.assertRaises(ValueError):
            self.resolve(
                "bill-entry",
                {**self.examples["bill-entry"], "review_mode": "only_exceptions"},
                require_review=True,
            )

    def test_unknown_settings_unsupported_formats_and_traversal_rejected(self):
        for key, changes in [
            ("bill-entry", {"input_format": "video"}),
            ("bill-entry", {"output_mode": "tally"}),
            ("bill-entry", {"allowed_source_ids": ["other-tenant"]}),
            ("source-discovery", {"max_files": 0}),
            ("source-discovery", {"scope_paths": ["../outside"]}),
            ("source-discovery", {"scope_paths": ["/absolute"]}),
            ("source-discovery", {"scope_paths": ["nested/../../outside"]}),
        ]:
            with self.subTest(key=key, changes=changes), self.assertRaises(ValidationError):
                self.resolve(key, {**self.examples[key], **changes})

    def test_missing_catalog_is_not_silently_defaulted(self):
        values = dict(self.examples["bill-entry"])
        values.pop("catalog_version")
        with self.assertRaises(ValidationError):
            self.resolve("bill-entry", values)

    def test_run_requires_explicit_business_schema_selection(self):
        for key in ("schema_id", "schema_version"):
            values = dict(self.examples["bill-entry"])
            values.pop(key)
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.resolve("bill-entry", values)


if __name__ == "__main__":
    unittest.main()
