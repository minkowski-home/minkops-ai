"""Workflow contracts: tool-session definitions, their pinned bundles and layered run configuration."""

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import ValidationError

from minkops_platform.workflows import load_definition, resolve_run_config

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / "employees/accounts-desk/workflows"


class WorkflowContractTests(unittest.TestCase):
    def test_both_desk_workflows_are_tool_sessions_pinned_with_their_handler_and_instructions(self):
        for key, handler, stages in (("bill-entry", "desk.bill", []), ("statement-entry", "desk.statement", ["layout"])):
            with self.subTest(key=key):
                definition = load_definition(WORKFLOWS / key)
                bundle = definition.session_bundle
                self.assertEqual((definition.metadata["owner"], definition.metadata["handler"]),
                                 ("accounts-desk", handler))
                self.assertEqual((bundle["key"], bundle["definition_version"], bundle["model"], bundle["reasoning_effort"]),
                                 (key, definition.metadata["version"], "gpt-6-luna", "medium"))
                self.assertEqual(sorted(bundle["stages"]), stages)
                # The skill's manifest is checked, then left out of what a session is told.
                self.assertFalse(bundle["instructions"].startswith("---"))
                self.assertIn(bundle["instructions"], definition.instructions)

    def test_a_run_configuration_layers_defaults_preferences_and_its_own_values(self):
        definition = load_definition(WORKFLOWS / "bill-entry")
        preferences = {"review_mode": "only_exceptions"}
        values = {"company_mode": "locked", "locked_company_guid": "guid-1"}
        resolved = resolve_run_config(definition, preferences, values)
        self.assertEqual(resolved, {"review_mode": "only_exceptions", "company_mode": "locked",
                                    "locked_company_guid": "guid-1"})
        resolved["review_mode"] = "all_outputs"
        self.assertEqual(preferences, {"review_mode": "only_exceptions"})
        self.assertEqual(resolve_run_config(definition, {"review_mode": "all_outputs"}, {})["company_mode"], "infer")

    def test_unknown_or_invalid_settings_are_refused(self):
        bill, statement = load_definition(WORKFLOWS / "bill-entry"), load_definition(WORKFLOWS / "statement-entry")
        for definition, values in ((bill, {"input_format": "mixed"}), (bill, {"review_mode": "sometimes"}),
                                   (bill, {"company_mode": "chosen"}), (statement, {"branch_mapping_file_id": 5})):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                resolve_run_config(definition, {"review_mode": "all_outputs"}, values)

    def test_a_definition_must_name_its_handler_and_sessions_and_nothing_hosted(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "bill-entry"
            shutil.copytree(WORKFLOWS / "bill-entry", directory)
            original = json.loads((directory / "workflow.json").read_text())
            for change in ({"handler": None}, {"sessions": None}, {"execution": {"environment": "openai_hosted"}}):
                descriptor = {key: value for key, value in {**original, **change}.items() if value is not None}
                (directory / "workflow.json").write_text(json.dumps(descriptor))
                with self.subTest(change=change), self.assertRaises(ValidationError):
                    load_definition(directory)


if __name__ == "__main__":
    unittest.main()
