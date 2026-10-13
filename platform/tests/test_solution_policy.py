"""Client composition restricts writes independently of operator preferences."""

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import ValidationError
from minkops_platform.solution_policy import bind_definition, validate_destination, validate_option
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

    def test_mock_disables_excel_discovery_with_the_same_tool_switch(self):
        original = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/source-discovery")
        bound = bind_definition(original, "mock-client")
        spec = bound.tenant_schema["properties"]["destination_mode"]
        self.assertEqual(spec["x-enabled-options"], ["tally"])
        validate_option(bound.tenant_schema, "destination_mode", "tally")
        for mode in ("excel", "both"):
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                validate_option(bound.tenant_schema, "destination_mode", mode)

    def test_enabled_tools_only_restrict_options_that_need_a_disabled_tool(self):
        original = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry")
        with tempfile.TemporaryDirectory() as root:
            for tools, expected in ((["excel", "tally"], None), (["excel"], ["excel_in_place", "draft_excel"])):
                with self.subTest(tools=tools):
                    policy = Path(root, "solutions", "client", "workflow-policy.json")
                    policy.parent.mkdir(parents=True, exist_ok=True)
                    policy.write_text(json.dumps({"enabled_tools": tools}))
                    bound = bind_definition(original, "client", repository_root=Path(root))
                    spec = bound.tenant_schema["properties"]["output_mode"]
                    self.assertEqual(spec.get("x-enabled-options"), expected)
            policy.write_text(json.dumps({"enabled_tools": []}))
            with self.assertRaises(ValueError):
                bind_definition(original, "client", repository_root=Path(root))
