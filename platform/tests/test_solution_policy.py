"""Client composition restricts writes independently of operator preferences."""

import unittest

from jsonschema import ValidationError
from minkops_platform.solution_policy import bind_definition, validate_destination
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import load_definition, validate


class SolutionPolicyTests(unittest.TestCase):
    def test_solution_without_overrides_keeps_shared_definition(self):
        original = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry")
        self.assertIs(bind_definition(original, "unconfigured-client"), original)

    def test_mock_keeps_choices_visible_but_only_allows_tally(self):
        original = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry")
        bound = bind_definition(original, "mock-client")
        spec = bound.tenant_schema["properties"]["output_mode"]
        self.assertIn("both_in_place", spec["enum"])
        self.assertEqual(spec["x-enabled-options"], ["tally_in_place"])
        validate_destination(bound.tenant_schema, "tally_in_place")
        for mode in ("excel_in_place", "both_in_place", "draft_excel"):
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                validate_destination(bound.tenant_schema, mode)
            with self.assertRaises(ValidationError):
                validate(bound.tenant_schema, {"review_mode": "all_outputs", "output_mode": mode})
        self.assertNotIn("allOf", original.tenant_schema["properties"]["output_mode"])

    def test_source_discovery_keeps_both_tools_available(self):
        original = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/source-discovery")
        bound = bind_definition(original, "mock-client")
        self.assertEqual(bound.tenant_schema, original.tenant_schema)
        for mode in ("excel", "tally", "both"):
            with self.subTest(mode=mode):
                validate(bound.tenant_schema, {
                    **original.metadata["tenant_defaults"], "destination_mode": mode
                })
