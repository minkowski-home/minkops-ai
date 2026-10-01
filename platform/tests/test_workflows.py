"""Contract and policy checks without agent calls or database requirements."""

import json
import unittest
from pathlib import Path

from jsonschema import ValidationError
from minkops_platform.workflows import (
    load_definition,
    resolve_run_config,
    validate,
    validate_output,
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
            ("bill-entry", {"input_format": "image"}),
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

    def output_case(self, data, schema):
        run = self.resolve("bill-entry")
        references = {key: run[key] for key in ("catalog_version", "schema_id", "schema_version")}
        result = {
            **references,
            "records": [
                {
                    "source_file_id": "rajtrack-01",
                    "data": data,
                    "evidence": [],
                    "findings": [],
                    "review_required": True,
                    "reconciliation_status": "insufficient_evidence",
                }
            ],
            "findings": [],
            "artifact_id": None,
            "status": "review_required",
        }
        return run, result, {**references, "schema": schema}

    def check_output(self, case):
        run, result, confirmed = case
        validate_output(
            self.definition("bill-entry"), result, run_config=run, confirmed_schema=confirmed
        )

    def test_different_client_fields_use_the_same_envelope(self):
        for data, properties in [
            (
                {"invoice_ref": "A-1", "payable": "18.99"},
                {"invoice_ref": {"type": "string"}, "payable": {"type": "string"}},
            ),
            (
                {"project_code": "SITE-A", "vehicle_number": "TEST-123", "amount": 19},
                {
                    "project_code": {"type": "string"},
                    "vehicle_number": {"type": "string"},
                    "amount": {"type": "integer"},
                },
            ),
        ]:
            with self.subTest(data=data):
                self.check_output(
                    self.output_case(
                        data,
                        {
                            "type": "object",
                            "properties": properties,
                            "required": list(properties),
                            "additionalProperties": False,
                        },
                    )
                )

    def test_business_data_requires_second_validation_layer(self):
        schema = {
            "type": "object",
            "properties": {"project_code": {"type": "string"}},
            "required": ["project_code"],
            "additionalProperties": False,
        }
        for data in [{}, {"project_code": 42}, {"project_code": "A", "unknown": True}]:
            with self.subTest(data=data):
                case = self.output_case(data, schema)
                validate(self.definition("bill-entry").output_schema, case[1])
                with self.assertRaises(ValidationError):
                    self.check_output(case)

    def test_business_types_and_dates_follow_the_confirmed_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "payable": {"type": "string", "pattern": r"^\d+\.\d{2}$"},
                "issued_on": {"type": "string", "format": "date"},
            },
            "required": ["payable", "issued_on"],
            "additionalProperties": False,
        }
        for data in [
            {"payable": 18.99, "issued_on": "2026-10-01"},
            {"payable": "18.99", "issued_on": "2026-02-30"},
        ]:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                self.check_output(self.output_case(data, schema))

    def test_schema_references_must_match_the_run(self):
        for key in ("catalog_version", "schema_id", "schema_version"):
            for index in (1, 2):
                case = self.output_case({}, {"type": "object"})
                case[index][key] = "different"
                with self.subTest(key=key, index=index), self.assertRaises(ValueError):
                    self.check_output(case)

    def test_business_schema_cannot_fetch_external_references(self):
        with self.assertRaises(ValueError):
            self.check_output(
                self.output_case(
                    {},
                    {
                        "type": "object",
                        "$ref": "https://example.invalid/schema.json",
                    },
                )
            )

    def test_result_needs_envelope_even_when_business_fields_are_valid(self):
        case = self.output_case({"custom": 1}, {"type": "object"})
        del case[1]["records"][0]["evidence"]
        with self.assertRaises(ValidationError):
            self.check_output(case)

    def test_run_requires_explicit_business_schema_selection(self):
        for key in ("schema_id", "schema_version"):
            values = dict(self.examples["bill-entry"])
            values.pop(key)
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.resolve("bill-entry", values)


if __name__ == "__main__":
    unittest.main()
