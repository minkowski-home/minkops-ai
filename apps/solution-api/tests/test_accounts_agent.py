"""Verify hosted configuration and turn-specific artifact selection offline."""

import base64
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from minkops_platform.accounts.agent import execute, read_result


class HostedAdapterTests(TestCase):
    def client(self):
        c = MagicMock()
        c.beta.agents.sessions.artifacts.list.return_value = [
            SimpleNamespace(id="output", turn_id="turn", path="/workspace/outputs/result.json")
        ]
        c.beta.agents.sessions.artifacts.content.return_value.content = b'{"sheets": []}'
        event = SimpleNamespace(
            type="agent.session.turn.completed",
            model_dump=lambda **_: {"session_id": "session", "turn_id": "turn"},
        )
        c.beta.agents.sessions.create.return_value.__iter__.return_value = iter([event])
        return c

    def test_requested_model_hosting_and_skill_archive(self):
        c = self.client()
        callbacks = []
        execute("source-discovery", [], {"config": {}}, lambda *a: callbacks.append(a), client=c)
        args = c.beta.agents.sessions.create.call_args.kwargs
        self.assertEqual(args["agent"]["model"], "gpt-6-luna")
        env = args["environment"]
        self.assertEqual(env["type"], "openai_hosted")
        self.assertEqual(env["network"]["access"], "disabled")
        self.assertIn("openpyxl", env["packages"]["python"])
        skill = env["skills"][0]
        with ZipFile(BytesIO(base64.b64decode(skill["source"]["data"]))) as archive:
            self.assertIn("source-discovery/SKILL.md", archive.namelist())
            self.assertIn("source-discovery/execution-instructions.md", archive.namelist())
            self.assertIn("source-discovery/agent-output.schema.json", archive.namelist())
        self.assertTrue(callbacks)

    def test_only_exact_completed_turn_output_is_accepted(self):
        c = self.client()
        c.beta.agents.sessions.artifacts.list.return_value = [
            SimpleNamespace(id="wrong", turn_id="earlier", path="/workspace/outputs/result.json")
        ]
        with self.assertRaises(ValueError):
            read_result(c, "session", "turn")
        c.beta.agents.sessions.artifacts.content.assert_not_called()

    def test_completed_saved_session_does_not_replay_input(self):
        c = self.client()
        c.beta.agents.sessions.turns.retrieve.return_value.status = "completed"
        execute(
            "source-discovery",
            [],
            {"config": {}},
            lambda *a: None,
            client=c,
            session_id="session",
            turn_id="turn",
        )
        c.beta.agents.sessions.create.assert_not_called()


class FakeStream:
    """A provider event stream that may drop after its events."""

    def __init__(self, events, error=None):
        self.events, self.error = events, error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        yield from self.events
        if self.error:
            raise self.error


def provider_event(kind):
    return SimpleNamespace(type=kind, model_dump=lambda **_: {"session_id": "session", "turn_id": "turn"})


@patch("minkops_platform.runtime.openai_hosted.REATTACH_DELAY", 0)
class StreamRecoveryTests(TestCase):
    def client(self, drops):
        import httpx
        from openai import APIError

        c = HostedAdapterTests.client(None)
        error = APIError("stream interrupted", httpx.Request("GET", "https://api.test"), body=None)
        c.beta.agents.sessions.create.return_value = FakeStream(
            [provider_event("agent.session.turn.created")], error)
        c.beta.agents.sessions.turns.retrieve.return_value.status = "in_progress"
        c.beta.agents.sessions.events.stream.side_effect = [FakeStream([], error)] * (drops - 1) + [
            FakeStream([provider_event("agent.session.turn.completed")])]
        return c

    def test_dropped_stream_reattaches_to_the_same_turn_without_a_new_session(self):
        c = self.client(drops=2)
        result = execute("source-discovery", [], {"config": {}}, lambda *a: None, client=c)
        self.assertEqual(result, {"sheets": []})
        c.beta.agents.sessions.create.assert_called_once()
        self.assertEqual(c.beta.agents.sessions.events.stream.call_count, 2)

    def test_repeated_drops_stop_after_a_bounded_number_of_reattachments(self):
        from openai import APIError

        c = self.client(drops=10)
        with self.assertRaises(APIError):
            execute("source-discovery", [], {"config": {}}, lambda *a: None, client=c)
        c.beta.agents.sessions.create.assert_called_once()
        self.assertEqual(c.beta.agents.sessions.events.stream.call_count, 3)
