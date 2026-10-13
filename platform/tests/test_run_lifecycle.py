"""Recovery guarantees apply independently of Accounts or its persistence tables."""

from unittest import TestCase
from unittest.mock import MagicMock, patch


class RunLifecycleTests(TestCase):
    def setUp(self):
        # Persistence has separate PostgreSQL integration coverage.
        patcher = patch("minkops_platform.runtime.diagnostics.record")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("minkops_platform.runtime.lifecycle.record")
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_stream_chunks_are_aggregated_without_repeated_session_writes(self):
        from minkops_platform.runtime.lifecycle import execute_proposal

        connection, store = MagicMock(), MagicMock()
        run = self.make_run(config={"execution_snapshot": {}}, workflow_key="test")
        run["config"]["execution_snapshot"] = {"present": True}

        def execute(key, files, context, event, **kwargs):
            event("agent.session.turn.created", "session", "turn")
            for _ in range(500):
                event("agent.session.turn.output_text.delta", "session", "turn")
            event("agent.session.turn.completed", "session", "turn")
            return {}

        with patch("minkops_platform.runtime.lifecycle.time.monotonic", return_value=0), \
             patch("minkops_platform.runtime.lifecycle.record") as audit:
            execute_proposal(connection, store, run, [], {}, execute)
        store.save_session.assert_called_once_with(connection, run, "session", "turn")
        self.assertEqual(connection.commit.call_count, 2)  # IDs, then raw result.
        self.assertEqual(audit.call_count, 3)  # Creation, aggregate, completion.
        activity = audit.call_args_list[1]
        self.assertEqual(activity.args[2], "hosted.activity")
        self.assertEqual(activity.kwargs["details"]["event_counts"],
                         {"agent.session.turn.output_text.delta": 500})

    def test_stream_heartbeat_is_bounded_and_retains_recovery_ids(self):
        from minkops_platform.runtime.lifecycle import execute_proposal

        connection, store = MagicMock(), MagicMock()
        run = self.make_run(config={"execution_snapshot": {"present": True}},
                            workflow_key="test", session_id="session", turn_id="turn")
        clock = [0]

        def execute(key, files, context, event, **kwargs):
            clock[0] = 5
            event("agent.output.command_execution_output.delta", None, None)
            store.save_session.assert_not_called()
            clock[0] = 10
            event("agent.session.turn.item.done", None, None)
            store.save_session.assert_called_once_with(connection, run, "session", "turn")
            event("agent.session.turn.output_text.delta", None, None)
            return {}

        with patch("minkops_platform.runtime.lifecycle.time.monotonic", side_effect=lambda: clock[0]), \
             patch("minkops_platform.runtime.lifecycle.record") as audit:
            execute_proposal(connection, store, run, [], {}, execute)
        self.assertEqual(audit.call_count, 2)  # Timed aggregate, final remainder.
        self.assertEqual(run["session_id"], "session")
        self.assertEqual(run["turn_id"], "turn")

    def test_recovery_ids_are_committed_even_when_first_seen_on_a_chunk(self):
        from minkops_platform.runtime.lifecycle import execute_proposal

        connection, store = MagicMock(), MagicMock()
        run = self.make_run(config={"execution_snapshot": {"present": True}}, workflow_key="test")

        def execute(key, files, context, event, **kwargs):
            event("agent.session.created", "session", None)
            event("agent.session.turn.output_text.delta", "session", "turn")
            self.assertEqual(store.save_session.call_count, 2)
            self.assertEqual(connection.commit.call_count, 2)
            raise RuntimeError("Provider disconnected")

        with patch("minkops_platform.runtime.lifecycle.time.monotonic", return_value=0), \
             patch("minkops_platform.runtime.lifecycle.record") as audit:
            with self.assertRaisesRegex(RuntimeError, "Provider disconnected"):
                execute_proposal(connection, store, run, [], {}, execute)
        store.save_result.assert_not_called()
        self.assertEqual(audit.call_args.args[2], "hosted.activity")
        self.assertEqual(audit.call_args.kwargs["details"]["event_counts"],
                         {"agent.session.turn.output_text.delta": 1})
