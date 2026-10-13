"""Warm compute must not share conversations, run paths, or uncertain work."""

import base64
import hashlib
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock


class HostedWorkspaceTests(TestCase):
    def test_namespace_preserves_business_bytes_and_rebinds_only_derived_indexes(self):
        from minkops_platform.runtime.openai_hosted import workspace_inputs

        bill = {"id": "bill", "path": "bill.pdf", "content": b"original bill"}
        index = {"id": "index", "path": "index.json", "workspace_references": True,
                 "content": b'{"candidate":{"path":"/workspace/inputs/bill.pdf","offset":0}}'}
        context = {"files": [{"path": "/workspace/inputs/index.json", "sha256": "old"}],
                   "description": "/workspace/inputs/bill.pdf"}
        uploads, bound = workspace_inputs([bill, index], context, "/workspace/runs/run")
        by_path = {f["path"]: base64.b64decode(f["data"]) for f in uploads}
        self.assertEqual(by_path["/workspace/runs/run/inputs/bill.pdf"], b"original bill")
        rebound = json.loads(by_path["/workspace/runs/run/inputs/index.json"])
        self.assertEqual(rebound["candidate"]["path"], "/workspace/runs/run/inputs/bill.pdf")
        self.assertEqual(bound["description"], context["description"])
        self.assertNotEqual(bound["files"][0]["sha256"], "old")
        self.assertEqual(json.loads(index["content"])["candidate"]["path"], "/workspace/inputs/bill.pdf")
        self.assertEqual(bound["files"][0]["sha256"], hashlib.sha256(by_path["/workspace/runs/run/inputs/index.json"]).hexdigest())

    def test_schema_property_named_path_is_not_an_execution_reference(self):
        from minkops_platform.runtime.openai_hosted import workspace_inputs

        context = {"schema": {"properties": {"path": {"type": "string"}}}}
        self.assertEqual(workspace_inputs([], context, "/workspace/runs/run")[1], context)

    def test_reused_environment_uses_fresh_session_and_unique_artifact_path(self):
        from minkops_platform.runtime.openai_hosted import execute

        c = MagicMock()
        event = SimpleNamespace(type="agent.session.turn.completed",
                                model_dump=lambda **k: {"session_id": "session", "turn_id": "turn"})
        c.beta.agents.sessions.create.return_value.__iter__.return_value = iter([event])
        output = "/workspace/outputs/run/result.json"
        c.beta.agents.sessions.artifacts.list.return_value = [SimpleNamespace(
            id="output", path=output, turn_id="turn")]
        c.beta.agents.sessions.artifacts.content.return_value.content = b'{"records":[]}'
        lease = MagicMock(workspace={"root": "/workspace/runs/run", "result_path": output})
        lease.prepare.return_value = "environment"
        result = execute("test", [], {}, lambda *args: None, instructions="Use /workspace/context.json",
                         execution_instructions="", model="gpt-6-luna", packages=[],
                         skill_files={"SKILL.md": "instructions"}, skill_description="Test",
                         environment_lease=lease, client=c)
        self.assertEqual(result, {"records": []})
        args = c.beta.agents.sessions.create.call_args.kwargs
        self.assertEqual(args["environment"], {"type": "openai_hosted", "environment_id": "environment"})
        self.assertIn("/workspace/runs/run/context.json", args["agent"]["instructions"])
        self.assertIn(output, args["input"])
        self.assertGreater(c.beta.agents.environments.files.create.call_count, 0)

    def test_recovery_does_not_attach_upload_or_create_even_after_environment_expiry(self):
        from minkops_platform.runtime.openai_hosted import execute

        c = MagicMock()
        c.beta.agents.sessions.turns.retrieve.return_value.status = "completed"
        output = "/workspace/outputs/run/result.json"
        c.beta.agents.sessions.artifacts.list.return_value = [SimpleNamespace(
            id="output", path=output, turn_id="turn")]
        c.beta.agents.sessions.artifacts.content.return_value.content = b'{}'
        execute("test", [], {}, lambda *args: None, instructions="", execution_instructions="",
                model="", packages=[], session_id="session", turn_id="turn", client=c,
                workspace={"root": "/workspace/runs/run", "result_path": output})
        c.beta.agents.sessions.create.assert_not_called()
        c.beta.agents.environments.files.create.assert_not_called()
        c.beta.agents.environments.retrieve.assert_not_called()

    def test_pinned_workflow_recovery_reads_the_saved_workspace(self):
        from minkops_platform.accounts.agent import execute
        from minkops_platform.resources import REPOSITORY_ROOT
        from minkops_platform.workflows import load_definition

        definition = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry")
        output = "/workspace/outputs/run/result.json"
        c = MagicMock()
        c.beta.agents.sessions.turns.retrieve.return_value.status = "completed"
        c.beta.agents.sessions.artifacts.list.return_value = [SimpleNamespace(
            id="result", path=output, turn_id="turn")]
        c.beta.agents.sessions.artifacts.content.return_value.content = b'{"records":[]}'
        result = execute("bill-entry", [], {"config": {
            "execution_snapshot": definition.execution_snapshot,
            "hosted_workspace": {"root": "/workspace/runs/run", "result_path": output},
        }}, lambda *args: None, session_id="session", turn_id="turn", client=c)
        self.assertEqual(result, {"records": []})
        c.beta.agents.sessions.create.assert_not_called()

    def test_ambiguous_creation_is_not_retried_on_fresh_compute(self):
        from minkops_platform.runtime.openai_hosted import execute

        c = MagicMock()
        c.beta.agents.sessions.create.side_effect = TimeoutError()
        lease = MagicMock(workspace={"root": "/workspace/runs/run",
                                    "result_path": "/workspace/outputs/run/result.json"})
        lease.prepare.return_value = "environment"
        with self.assertRaises(TimeoutError):
            execute("test", [], {}, lambda *args: None, instructions="Test", execution_instructions="",
                    model="test", packages=[], skill_description="Test", environment_lease=lease, client=c)
        c.beta.agents.sessions.create.assert_called_once()

    def test_stop_during_upload_prevents_session_creation(self):
        from minkops_platform.runtime.openai_hosted import execute

        c = MagicMock()
        lease = MagicMock(workspace={"root": "/workspace/runs/run",
                                    "result_path": "/workspace/outputs/run/result.json"})
        lease.check_start.side_effect = ValueError("Stopped")
        with self.assertRaisesRegex(ValueError, "Stopped"):
            execute("test", [], {}, lambda *args: None, instructions="Test", execution_instructions="",
                    model="test", packages=[], skill_description="Test", environment_lease=lease, client=c)
        c.beta.agents.sessions.create.assert_not_called()
