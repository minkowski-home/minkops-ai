"""The worker and connectors must remain usable without the web application."""

import ast
import hashlib
import importlib
from pathlib import Path
from unittest import TestCase


class PackageBoundaryTests(TestCase):
    def test_shared_services_import_without_web_application_dependencies(self):
        for name in (
            "minkops_platform.desktop",
            "minkops_platform.accounts.service",
            "minkops_platform.accounts.repository",
            "minkops_platform.accounts.checks",
            "minkops_platform.accounts.catalog",
            "minkops_platform.accounts.agent",
            "minkops_platform.artifacts",
            "minkops_platform.accounts.worker",
            "minkops_platform.runtime.openai_hosted",
            "minkops_platform.runtime.workflow",
            "minkops_platform.runtime.bundles",
            "minkops_platform.runtime.lifecycle",
            "minkops_platform.accounts.run_store",
            "minkops_connectors.excel",
        ):
            module = importlib.import_module(name)
            tree = ast.parse(Path(module.__file__).read_text())
            for node in ast.walk(tree):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
                self.assertFalse(any(n.startswith(("minkops_api", "fastapi")) for n in names), name)
                if name.startswith("minkops_connectors"):
                    self.assertFalse(any(n.startswith("minkops_platform") for n in names), name)

    def test_versioned_workflow_prompts_match_reviewed_schema_context_contract(self):
        from minkops_platform.accounts.agent import bill_prompt, discovery_prompt

        self.assertEqual(
            hashlib.sha256(discovery_prompt().encode()).hexdigest(),
            "df060986608b53b347becf3eadc9def5ad45d7f52eb68ff9644345b19ec4844c",
        )
        self.assertEqual(
            hashlib.sha256(bill_prompt().encode()).hexdigest(),
            "52eb3ca4733abbb762a978347fdef2f2f103beb3eb92445cbeeefee792c87ad6",
        )
