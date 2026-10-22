"""Workflow contracts: tool-session definitions, their pinned bundles and layered run configuration."""

import json
import re
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


def answer_names(schema, found=None):
    """Every property name and enum value an answer schema declares."""
    found = set() if found is None else found
    if isinstance(schema, dict):
        found.update(schema.get("properties", {}))
        found.update(value for value in schema.get("enum", []) if isinstance(value, str))
        for value in schema.values():
            answer_names(value, found)
    elif isinstance(schema, list):
        for value in schema:
            answer_names(value, found)
    return found


def resolves(schema, path):
    """Whether a dotted path names a property of the answer schema, at any depth."""
    if not path:
        return True
    for node in [schema, *schema.get("anyOf", []), schema.get("items") or {}]:
        if isinstance(node, dict):
            if path[0] in node.get("properties", {}) and resolves(node["properties"][path[0]], path[1:]):
                return True
            if any(resolves(child, path) for child in node.get("properties", {}).values()):
                return True
    return False


class InstructionContractTests(unittest.TestCase):
    """Instructions name only what exists: a field renamed in the answer's schema cannot leave them behind."""

    def check(self, instructions, schema, known):
        for name in re.findall(r"`([a-z][a-z_.]*)`", instructions):
            with self.subTest(name=name):
                if "." in name:
                    self.assertTrue(resolves(schema, name.split(".")), f"{name} is no path of the answer")
                else:
                    self.assertIn(name, answer_names(schema) | known)

    def test_the_bill_instructions_name_only_fields_tools_and_codes_that_exist(self):
        from minkops_platform.accounts import bill_entry, desk_tools
        # Fields of the session's input and of lookup answers, which no answer schema declares.
        given = {"decided_bills", "gst_duty", "description"}
        self.check(load_definition(WORKFLOWS / "bill-entry").instructions, bill_entry.PROPOSAL.tool.input_schema,
                   set(desk_tools.TOOLS) | set(bill_entry.BILL_TOOLS) | given)

    def test_the_statement_instructions_name_only_fields_tools_and_codes_that_exist(self):
        from minkops_platform.accounts import desk_tools, statement_entry
        definition = load_definition(WORKFLOWS / "statement-entry")
        # A lookup answer's field: a ledger that keeps bill-by-bill balances.
        self.check(definition.instructions, statement_entry.ROWS.tool.input_schema,
                   set(desk_tools.TOOLS) | set(statement_entry.CHUNK_TOOLS) | {"bill_by_bill"})
        self.check(definition.session_bundle["stages"]["layout"], statement_entry.READING.tool.input_schema, set())
