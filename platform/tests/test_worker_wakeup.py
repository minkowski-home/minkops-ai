"""Durable wake-ups survive dispatch failure and never acknowledge newer work."""

import os
import threading
import unittest
from unittest.mock import patch

import factory
import psycopg
from psycopg.rows import dict_row

from minkops_platform import work


def test_dispatch_coalesces_before_allocating_another_database_connection(monkeypatch):
    from minkops_platform import worker_hosting
    entered, release = threading.Event(), threading.Event()
    calls = []
    def dispatch(*args):
        calls.append(True)
        entered.set()
        assert release.wait(3)
        return True
    monkeypatch.setattr(worker_hosting, '_dispatch', dispatch)
    results = []
    thread = threading.Thread(target=lambda: results.append(worker_hosting.dispatch('unused', None)))
    thread.start()
    try:
        assert entered.wait(3)
        assert worker_hosting.dispatch('unused', None) is False
        assert calls == [True]
    finally:
        release.set()
        thread.join(3)
    assert results == [True]


def test_dispatch_connection_failure_releases_its_process_fence(monkeypatch):
    from minkops_platform import worker_hosting
    def unavailable(*args, **kwargs):
        raise psycopg.OperationalError('connection budget temporarily unavailable')
    monkeypatch.setattr(worker_hosting.psycopg, 'connect', unavailable)
    assert worker_hosting.dispatch('unused', None) is False
    assert worker_hosting.dispatch('unused', None) is False


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class WorkerWakeupTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(self.url) as c:
            c.execute(
                "UPDATE worker_wakeup SET generation=generation+1,acknowledged=0,lease_until=NULL"
            )
        self.connection = factory.connect()
        self.addCleanup(self.connection.close)

    def test_failed_dispatch_remains_durable_and_success_coalesces(self):
        from minkops_platform.worker_hosting import dispatch

        def fail():
            raise OSError("temporary provider failure")

        self.assertFalse(dispatch(self.url, fail))
        calls = []
        self.assertTrue(dispatch(self.url, lambda: calls.append(True)))
        self.assertFalse(dispatch(self.url, lambda: calls.append(True)))
        self.assertEqual(len(calls), 1)

    def drain(self, host, **options):
        from minkops_platform import worker_hosting
        with patch.object(worker_hosting.time, "sleep"), patch.object(worker_hosting, "enforce") as enforce:
            return worker_hosting.drain(self.url, host, **options), enforce.call_count

    def wakeup(self):
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            return c.execute("SELECT * FROM worker_wakeup").fetchone()

    def test_an_idle_drain_acknowledges_only_the_generation_it_observed(self):
        def bump():
            with psycopg.connect(self.url) as c:
                c.execute("UPDATE worker_wakeup SET generation=generation+1")
        host = Lanes(busy=[], settled=[True, True], during=[bump])
        acknowledged, _ = self.drain(host)
        self.assertTrue(acknowledged)
        row = self.wakeup()
        self.assertEqual(row["generation"], row["acknowledged"])
        self.assertIsNone(row["lease_until"])
        self.assertEqual(host.waits, 2)  # the work that arrived during the first look is looked at again

    def test_the_runner_lease_is_published_while_lanes_work_and_cleared_on_acknowledging(self):
        seen = []
        def observe():
            row = self.wakeup()
            seen.append((row["lease_until"] is not None, row["generation"] > row["acknowledged"]))
        acknowledged, _ = self.drain(Lanes(busy=[True], settled=[True], during=[observe, observe]))
        self.assertTrue(acknowledged)
        self.assertEqual(seen, [(True, True), (True, True)])
        self.assertIsNone(self.wakeup()["lease_until"])

    def test_busy_or_unsettled_lanes_delay_the_acknowledgement_while_run_limits_keep_being_enforced(self):
        host = Lanes(busy=[True, True], settled=[False, True])
        acknowledged, monitored = self.drain(host)
        self.assertTrue(acknowledged)
        self.assertEqual((host.checks, monitored), (2, 4))

    def test_another_runner_keeps_the_drain_from_starting(self):
        from minkops_platform.worker_hosting import RUNNER_LOCK
        with psycopg.connect(self.url, autocommit=True) as c:
            c.execute("SELECT pg_advisory_lock(%s)", (RUNNER_LOCK,))
            host = Lanes(busy=[], settled=[])
            self.assertEqual(self.drain(host), (False, 0))
            self.assertEqual(host.waits, 0)

    def test_a_drain_that_reaches_its_deadline_leaves_the_work_to_a_successor(self):
        host = Lanes(busy=[], settled=[])
        acknowledged, _ = self.drain(host, max_seconds=0)
        self.assertFalse(acknowledged)
        self.assertTrue(host.stopped_claiming)
        row = self.wakeup()
        self.assertGreater(row["generation"], row["acknowledged"])
        self.assertIsNone(row["lease_until"])

    def test_a_failing_drain_releases_its_lock_and_lease_for_a_successor(self):
        from minkops_platform.worker_hosting import RUNNER_LOCK
        def fail():
            raise RuntimeError("lane failure")
        with self.assertRaisesRegex(RuntimeError, "lane failure"):
            self.drain(Lanes(busy=[True], settled=[], during=[fail]))
        self.assertIsNone(self.wakeup()["lease_until"])
        with psycopg.connect(self.url, autocommit=True) as c:
            self.assertTrue(c.execute("SELECT pg_try_advisory_lock(%s)", (RUNNER_LOCK,)).fetchone()[0])
            c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))

    def test_a_queued_item_bumps_the_wake_up_only_when_it_commits(self):
        before = self.wakeup()["generation"]
        tenant = factory.tenant(self.connection)
        factory.run(self.connection, tenant, factory.client(self.connection, tenant),
                    factory.workflow(self.connection, tenant), factory.user(self.connection, tenant),
                    [work.ItemSpec("bill", {"file_id": "a"})])
        self.assertEqual(self.connection.execute("SELECT generation FROM worker_wakeup").fetchone()["generation"],
                         before + 1)
        self.connection.rollback()
        self.assertEqual(self.wakeup()["generation"], before)


class Lanes:
    """A lanes host as drain sees it: busy for some looks, then settled or not, running a step during each wait."""

    def __init__(self, *, busy, settled, during=()):
        self.busy, self.settled_answers, self.during = list(busy), list(settled), list(during)
        self.waits = self.checks = 0
        self.stopped_claiming = False

    def wait_idle(self, timeout):
        self.waits += 1
        if self.during:
            self.during.pop(0)()
        return not (self.busy.pop(0) if self.busy else False)

    def settled(self, connection):
        self.checks += 1
        return self.settled_answers.pop(0) if self.settled_answers else True

    def stop_claiming(self):
        self.stopped_claiming = True


if __name__ == "__main__":
    unittest.main()
