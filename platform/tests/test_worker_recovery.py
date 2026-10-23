"""The recovery sweep dispatches a worker only for work one can do, never for idle or blocked items."""
import os
import unittest

import factory
import psycopg
from psycopg.rows import dict_row

from db.testing import disposable_database
from minkops_platform import work

BLOCKER = {"kind": "sync", "ref": "pc-1"}


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        context = disposable_database(os.environ["TEST_DATABASE_URL"])
        self.url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.calls = []

    def item(self, **spec):
        """A run with one item, its wake-up already consumed as if a notification were lost."""
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            tenant = factory.tenant(c)
            run = factory.run(c, tenant, factory.client(c, tenant), factory.workflow(c, tenant), factory.user(c, tenant),
                              [work.ItemSpec("bill", {"file_id": "a"}, **spec)])
            c.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL")
            return tenant, run, c.execute("SELECT * FROM run_items WHERE run_id=%s", (run["id"],)).fetchone()

    def recover(self):
        from minkops_platform.worker_hosting import recover
        return recover(self.url, lambda: self.calls.append(True))

    def test_an_old_notification_with_nothing_to_do_starts_no_worker(self):
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE worker_wakeup SET generation=generation+1")
        self.assertFalse(self.recover())
        self.assertEqual(self.calls, [])

    def test_a_queued_item_whose_wake_up_was_lost_is_recovered_once(self):
        self.item()
        self.assertTrue(self.recover())
        self.assertFalse(self.recover())  # the dispatch's lease coalesces a second sweep
        self.assertEqual(len(self.calls), 1)

    def test_a_waiting_item_is_recovered_only_once_its_blocker_is_released(self):
        tenant, _, _ = self.item(waiting_on=BLOCKER)
        self.assertFalse(self.recover())
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            work.release(c, tenant["id"], BLOCKER)
            # The release's notification and dispatch were lost.
            c.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL")
        self.assertTrue(self.recover())
        self.assertEqual(len(self.calls), 1)

    def test_an_item_of_a_stopped_task_is_not_runnable(self):
        _, run, _ = self.item()
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE tasks SET control_state='stopped' WHERE id=%s", (run["task_id"],))
        self.assertFalse(self.recover())

    def test_a_finished_session_still_open_at_the_provider_wakes_a_worker_to_close_it(self):
        _, _, item = self.item()
        with psycopg.connect(self.url) as c:
            c.execute("""UPDATE run_items SET state='done', finished_at=now(), session_id='open-session'
                         WHERE id=%s""", (item["id"],))
            c.execute("""INSERT INTO item_sessions (tenant_id, item_id, session_id, attempt, finished_at)
                         VALUES (%s, %s, 'open-session', 1, now())""", (item["tenant_id"], item["id"]))
            c.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL")
        self.assertTrue(self.recover())

    def test_a_live_runner_is_not_disturbed(self):
        from minkops_platform.worker_hosting import RUNNER_LOCK
        self.item()
        with psycopg.connect(self.url, autocommit=True) as c:
            c.execute("SELECT pg_advisory_lock(%s)", (RUNNER_LOCK,))
            self.assertFalse(self.recover())
        self.assertEqual(self.calls, [])

    def test_a_stale_start_lease_is_recovered_but_a_fresh_one_is_left_to_start(self):
        self.item()
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes'")
        self.assertFalse(self.recover())
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '27 minutes'")
        self.assertTrue(self.recover())


if __name__ == "__main__":
    unittest.main()
