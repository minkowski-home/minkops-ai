"""Execution must use the complete launched revision, not today's checkout."""

import base64
import json
import shutil
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock
from zipfile import ZipFile

from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import load_definition


class ExecutionBundleTests(TestCase):
    def fixture(self, directory):
        target = Path(directory) / "source-discovery"
        shutil.copytree(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/source-discovery", target
        )
        metadata = json.loads((target / "workflow.json").read_text())
        metadata["execution"] = {
            "environment": "openai_hosted",
            "model": "gpt-6-luna",
            "python_packages": ["openpyxl", "pymupdf"],
            "instructions": "execution-instructions.md",
            "resources": ["scripts/check.py"],
            "result_path": "/workspace/outputs/proposal.json",
        }
        (target / "scripts").mkdir()
        (target / "scripts/check.py").write_text("print('original helper')\n")
        (target / "workflow.json").write_text(json.dumps(metadata))
        return target

    def client(self, path):
        client = MagicMock()
        client.beta.agents.sessions.artifacts.list.return_value = [
            SimpleNamespace(id="output", turn_id="turn", path=path)
        ]
        client.beta.agents.sessions.artifacts.content.return_value.content = b'{"sheets": []}'
        event = SimpleNamespace(
            type="agent.session.turn.completed",
            model_dump=lambda **_: {"session_id": "session", "turn_id": "turn"},
        )
        client.beta.agents.sessions.create.return_value.__iter__.return_value = iter([event])
        return client

    def test_entire_bundle_survives_checkout_changes_and_includes_helper_and_contracts(self):
        from minkops_platform.runtime.workflow import execute

        with TemporaryDirectory() as directory:
            target = self.fixture(directory)
            definition = load_definition(target)
            snapshot = deepcopy(definition.execution_snapshot)
            original_prompt = (target / "execution-instructions.md").read_text()
            (target / ".env").write_text("not an execution resource")
            shutil.rmtree(target)
            client = self.client("/workspace/outputs/proposal.json")
            execute(
                "source-discovery",
                [],
                {"config": {"execution_snapshot": snapshot}},
                lambda *args: None,
                client=client,
            )
        args = client.beta.agents.sessions.create.call_args.kwargs
        self.assertIn(original_prompt, args["agent"]["instructions"])
        self.assertEqual(args["agent"]["model"], "gpt-6-luna")
        self.assertEqual(args["environment"]["network"], {"access": "disabled"})
        with ZipFile(
            BytesIO(base64.b64decode(args["environment"]["skills"][0]["source"]["data"]))
        ) as archive:
            self.assertEqual(
                archive.read("source-discovery/scripts/check.py"), b"print('original helper')\n"
            )
            self.assertIn("source-discovery/agent-output.schema.json", archive.namelist())
            self.assertIn("source-discovery/execution-instructions.md", archive.namelist())
            self.assertNotIn("source-discovery/.env", archive.namelist())

    def test_snapshot_changes_when_any_execution_resource_changes(self):
        with TemporaryDirectory() as directory:
            target = self.fixture(directory)
            first = load_definition(target).execution_snapshot
            (target / "scripts/check.py").write_text("print('new helper')\n")
            second = load_definition(target).execution_snapshot
            self.assertNotEqual(first["sha256"], second["sha256"])

    def test_provider_skill_description_matches_manifest_instead_of_product_copy(self):
        with TemporaryDirectory() as directory:
            target = self.fixture(directory)
            skill = target / "SKILL.md"
            lines = skill.read_text().splitlines()
            lines = ["description: A concise provider-facing skill description."
                     if line.startswith("description:") else line for line in lines]
            skill.write_text("\n".join(lines))
            snapshot = load_definition(target).execution_snapshot
        self.assertEqual(
            snapshot["description"],
            "A concise provider-facing skill description.",
        )

    def test_bundle_rejects_tampered_content_before_creating_session(self):
        from minkops_platform.runtime.workflow import execute

        with TemporaryDirectory() as directory:
            snapshot = load_definition(self.fixture(directory)).execution_snapshot
        snapshot["files"]["scripts/check.py"] = "changed"
        client = self.client("/workspace/outputs/proposal.json")
        with self.assertRaisesRegex(ValueError, "digest"):
            execute(
                "source-discovery",
                [],
                {"config": {"execution_snapshot": snapshot}},
                lambda *a: None,
                client=client,
            )
        client.beta.agents.sessions.create.assert_not_called()

    def test_resources_cannot_escape_definition_or_follow_symlinks(self):
        for resource in ("../outside.py", "/tmp/outside.py", "scripts/link.py"):
            with self.subTest(resource=resource), TemporaryDirectory() as directory:
                target = self.fixture(directory)
                (Path(directory) / "outside.py").write_text("outside")
                (target / "scripts/link.py").symlink_to(Path(directory) / "outside.py")
                metadata = json.loads((target / "workflow.json").read_text())
                metadata["execution"]["resources"] = [resource]
                (target / "workflow.json").write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):
                    load_definition(target)

    def test_execution_does_not_dispatch_on_accounts_workflow_names(self):
        from minkops_platform.runtime.workflow import execute

        with TemporaryDirectory() as directory:
            target = self.fixture(directory)
            metadata = json.loads((target / "workflow.json").read_text())
            metadata["key"] = "inspect-inventory"
            (target / "workflow.json").write_text(json.dumps(metadata))
            renamed = target.rename(target.with_name("inspect-inventory"))
            snapshot = load_definition(renamed).execution_snapshot
        client = self.client("/workspace/outputs/proposal.json")
        self.assertEqual(
            execute(
                "inspect-inventory",
                [],
                {"config": {"execution_snapshot": snapshot}},
                lambda *a: None,
                client=client,
            ),
            {"sheets": []},
        )

    def test_recovered_turn_uses_pinned_artifact_path_without_replaying_input(self):
        from minkops_platform.runtime.workflow import execute

        with TemporaryDirectory() as directory:
            snapshot = load_definition(self.fixture(directory)).execution_snapshot
        client = self.client("/workspace/outputs/proposal.json")
        client.beta.agents.sessions.turns.retrieve.return_value.status = "completed"
        execute(
            "source-discovery",
            [],
            {"config": {"execution_snapshot": snapshot}},
            lambda *a: None,
            client=client,
            session_id="session",
            turn_id="turn",
        )
        client.beta.agents.sessions.create.assert_not_called()

    def test_bundle_cannot_be_used_for_a_different_run_version(self):
        from minkops_platform.runtime.workflow import execute

        with TemporaryDirectory() as directory:
            snapshot = load_definition(self.fixture(directory)).execution_snapshot
        client = self.client("/workspace/outputs/proposal.json")
        with self.assertRaisesRegex(ValueError, "definition version"):
            execute(
                "source-discovery",
                [],
                {"definition_version": "other", "config": {"execution_snapshot": snapshot}},
                lambda *a: None,
                client=client,
            )
        client.beta.agents.sessions.create.assert_not_called()
