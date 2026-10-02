"""Shared run identity and observations retain transaction and audit semantics."""

from unittest import TestCase
from unittest.mock import MagicMock


class RunControlTests(TestCase):
    def test_same_key_replays_only_the_same_payload_after_tenant_scoped_lock(self):
        from minkops_platform.errors import ServiceError
        from minkops_platform.run_controls import resolve_request

        connection = MagicMock()
        found = MagicMock()
        found.return_value = None
        fingerprint, previous = resolve_request(
            connection, "tenant", "key", {"a": 1, "b": 2}, found
        )
        self.assertIsNone(previous)
        connection.commit.assert_not_called()
        self.assertEqual(connection.execute.call_args.args[1], ("tenant:key",))
        found.return_value = {"request_hash": fingerprint}
        self.assertEqual(
            resolve_request(connection, "tenant", "key", {"b": 2, "a": 1}, found)[1],
            found.return_value,
        )
        with self.assertRaises(ServiceError):
            resolve_request(connection, "tenant", "key", {"a": 3}, found)

    def test_task_and_outbox_updates_belong_to_the_callers_transaction(self):
        from minkops_platform.run_controls import observe_task

        connection = MagicMock()
        observe_task(
            connection,
            tenant_id="tenant",
            task_id="task",
            run_id="run",
            state="review",
            summary="Review output",
            progress=70,
            event_prefix="account_run",
        )
        calls = connection.execute.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args[1], ("attention", "Review output", 70, "tenant", "task"))
        self.assertEqual(calls[2].args[1][:3], ("tenant", "account_run.review", "run"))
        connection.commit.assert_not_called()
