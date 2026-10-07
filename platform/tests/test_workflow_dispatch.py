"""Handlers and client policies extend execution without workflow-key branches."""

from copy import deepcopy
from unittest import TestCase

from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.runtime.application import binding_for, execution_config
from minkops_platform.workflows import load_definition


class DispatchTests(TestCase):
    def test_handler_is_declared_independently_of_workflow_identity(self):
        definition = load_definition(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry"
        )
        config = execution_config(
            definition, {}, authorized_bindings=[{"capability": "files.snapshot"}]
        )
        self.assertEqual(binding_for({"config": config}).handler, "accounts.bill")
        self.assertEqual(
            binding_for({"workflow_key": "another-key", "config": config}).handler, "accounts.bill"
        )

    def test_request_cannot_replace_trusted_runtime_or_tool_bindings(self):
        definition = load_definition(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry"
        )
        with self.assertRaisesRegex(ValueError, "reserved"):
            execution_config(definition, {"runtime_binding": {"handler": "anything"}})
        with self.assertRaisesRegex(ValueError, "reserved"):
            execution_config(definition, {"authorized_bindings": [{"id": "invented"}]})

    def test_missing_binding_only_supports_known_legacy_workflows(self):
        self.assertEqual(
            binding_for({"workflow_key": "bill-entry", "config": {}}).handler, "accounts.bill"
        )
        with self.assertRaises(ValueError):
            binding_for({"workflow_key": "unknown", "config": {}})

    def test_unknown_handler_fails_closed(self):
        from minkops_platform.runtime.application import get_handler

        with self.assertRaises(ValueError):
            get_handler("os.system")

    def test_unavailable_tool_requirement_fails_before_execution(self):
        from dataclasses import replace

        definition = load_definition(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry"
        )
        definition = replace(
            definition, metadata={**definition.metadata, "capabilities": ["mcp.unprovisioned"]}
        )
        with self.assertRaisesRegex(ValueError, "authorized capabilities"):
            execution_config(definition, {}, authorized_bindings=[{"capability": "files.snapshot"}])

    def test_changed_resource_binding_cannot_reach_the_paid_executor(self):
        from unittest.mock import MagicMock, patch

        from minkops_platform.runtime.application import process

        run = {
            "workflow_key": "bill-entry",
            "config": {
                "runtime_binding": {"handler": "accounts.bill"},
                "authorized_bindings": [
                    {"capability": "files.snapshot", "resource_id": "file", "sha256": "original"}
                ],
            },
        }
        handler = MagicMock()
        handler.prepare.return_value = ([{"id": "file", "sha256": "changed"}], {}, {})
        executor = MagicMock()
        with (
            patch("minkops_platform.runtime.application.get_handler", return_value=handler),
            self.assertRaisesRegex(ValueError, "authorized resource snapshot"),
        ):
            process(MagicMock(), MagicMock(), run, executor=executor, close_session=MagicMock())
        executor.assert_not_called()

    def test_new_definition_cannot_silently_change_an_installed_capability_binding(self):
        from dataclasses import replace
        from unittest.mock import patch

        from minkops_platform.runtime.launch import installed_definition

        definition = load_definition(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry"
        )
        changed = replace(
            definition, metadata={**definition.metadata, "capabilities": ["mcp.unprovisioned"]}
        )
        binding = {
            "definition": "accounts-desk/workflows/bill-entry",
            "handler": "accounts.bill",
            "presentation": "accounts-bill",
            "capabilities": ["files.snapshot"],
        }
        with (
            patch("minkops_platform.runtime.launch.load_definition", return_value=changed),
            self.assertRaisesRegex(ValueError, "Reinstall"),
        ):
            installed_definition(binding, "bill-entry")

    def test_policy_is_pinned_and_cannot_be_weakened_by_settings(self):
        from minkops_platform.runtime.application import enforce_policies

        result = {"records": [{"data": {"Amount": 50001}}], "findings": []}
        original = deepcopy(result)
        config = {
            "runtime_binding": {
                "handler": "accounts.bill",
                "policies": [
                    {"key": "review-threshold", "config": {"field": "Amount", "amount": 50000}}
                ],
            },
            "review_mode": "only_exceptions",
        }
        checked = enforce_policies(config, result)
        self.assertTrue(checked["requires_review"])
        self.assertEqual(result, original)
        self.assertNotIn(
            "requires_review", enforce_policies({"runtime_binding": {"policies": []}}, result)
        )
        self.assertFalse(
            enforce_policies(config, {"records": [{"data": {"Amount": 50000}}]})["requires_review"]
        )

    def test_guardrail_rejects_missing_or_nonnumeric_amount(self):
        from minkops_platform.runtime.application import enforce_policies

        config = {
            "runtime_binding": {
                "policies": [
                    {"key": "review-threshold", "config": {"field": "Amount", "amount": 50000}}
                ]
            }
        }
        for data in ({}, {"Amount": True}, {"Amount": "NaN"}, {"Amount": "invalid"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                enforce_policies(config, {"records": [{"data": data}]})
