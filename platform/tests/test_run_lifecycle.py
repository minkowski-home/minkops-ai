"""Recovery guarantees apply independently of Accounts or its persistence tables."""

from unittest import TestCase
from unittest.mock import MagicMock, patch


class RunLifecycleTests(TestCase):
    def make_run(self, **changes):
        return {
            "id": "run",
            "tenant_id": "tenant",
            "state": "queued",
            "session_id": None,
            "turn_id": None,
            "config": {},
            **changes,
        }

    def test_worker_reloads_after_lock_and_does_not_process_a_completed_run(self):
        from minkops_platform.runtime.lifecycle import work_once

        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {"held": True}
        store = MagicMock()
        store.candidates.return_value = [self.make_run()]
        store.get.return_value = self.make_run(state="completed")
        process = MagicMock()
        with patch("minkops_platform.runtime.lifecycle.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            self.assertFalse(work_once("unused", store, process))
        process.assert_not_called()
        self.assertIn("pg_advisory_unlock", connection.execute.call_args.args[0])

    def test_worker_does_not_replay_ambiguous_session_creation(self):
        from minkops_platform.runtime.lifecycle import work_once

        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {"held": True}
        store = MagicMock()
        run = self.make_run(state="executing")
        store.candidates.return_value = [run]
        store.get.return_value = run
        process = MagicMock()
        with patch("minkops_platform.runtime.lifecycle.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            self.assertTrue(work_once("unused", store, process))
        process.assert_not_called()
        self.assertIn("not be replayed", store.fail.call_args.args[2])

    def test_provider_exception_is_reported_by_class_without_secret_text(self):
        from minkops_platform.runtime.lifecycle import work_once

        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {"held": True}
        store = MagicMock()
        run = self.make_run()
        store.candidates.return_value = [run]
        store.get.return_value = run
        with patch("minkops_platform.runtime.lifecycle.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            work_once("unused", store, MagicMock(side_effect=RuntimeError("secret credential")))
        self.assertNotIn("secret", store.fail.call_args.args[2])
        self.assertIn("RuntimeError", store.fail.call_args.args[2])

    def test_raw_proposal_is_committed_before_schema_rejection(self):
        from jsonschema import ValidationError
        from minkops_platform.runtime.lifecycle import execute_proposal

        connection, store = MagicMock(), MagicMock()
        run = self.make_run(
            config={
                "execution_snapshot": {"present": True},
                "agent_output_schema": {"type": "object", "required": ["records"]},
            }
        )
        run["workflow_key"] = "any-workflow"
        with self.assertRaises(ValidationError):
            execute_proposal(
                connection, store, run, [], {"config": run["config"]}, lambda *a, **k: {}
            )
        store.save_result.assert_called_once_with(connection, run, {})
        connection.commit.assert_called_once()

    def test_unpinned_legacy_queued_run_cannot_create_a_new_session(self):
        from minkops_platform.runtime.lifecycle import execute_proposal

        executor = MagicMock()
        with self.assertRaisesRegex(ValueError, "execution bundle"):
            execute_proposal(MagicMock(), MagicMock(), self.make_run(), [], {}, executor)
        executor.assert_not_called()

    def test_event_persistence_precedes_result_and_cleanup_marks_only_success(self):
        from minkops_platform.runtime.lifecycle import close_run, execute_proposal

        connection, store = MagicMock(), MagicMock()
        run = self.make_run(config={"execution_snapshot": {"present": True}})

        def execute(key, files, context, event, **kwargs):
            event("agent.session.turn.created", "session", "turn")
            self.assertEqual(run["session_id"], "session")
            store.save_session.assert_called_once_with(connection, run, "session", "turn")
            return {"records": []}

        run["workflow_key"] = "any-workflow"
        execute_proposal(connection, store, run, [], {}, execute)
        close = MagicMock(side_effect=RuntimeError("unavailable"))
        close_run(connection, store, run, close_session=close)
        store.mark_closed.assert_not_called()
        close_run(connection, store, run, close_session=MagicMock())
        store.mark_closed.assert_called_once_with(connection, run)
