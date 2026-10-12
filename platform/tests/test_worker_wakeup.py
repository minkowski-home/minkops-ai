"""Durable wake-ups survive dispatch failure and never acknowledge newer work."""

import os
import threading
import unittest

import psycopg
from psycopg.rows import dict_row


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class WorkerWakeupTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(self.url) as c:
            c.execute(
                "UPDATE worker_wakeup SET generation=generation+1,acknowledged=0,lease_until=NULL"
            )

    def test_failed_dispatch_remains_durable_and_success_coalesces(self):
        from minkops_platform.worker_hosting import dispatch

        def fail():
            raise OSError("temporary provider failure")

        self.assertFalse(dispatch(self.url, fail))
        calls = []
        self.assertTrue(dispatch(self.url, lambda: calls.append(True)))
        self.assertFalse(dispatch(self.url, lambda: calls.append(True)))
        self.assertEqual(len(calls), 1)

    def test_idle_drain_acknowledges_only_observed_generation(self):
        from minkops_platform.worker_hosting import drain

        calls = []

        def work(url):
            calls.append(True)
            if len(calls) == 1:
                with psycopg.connect(url) as c:
                    c.execute("UPDATE worker_wakeup SET generation=generation+1")
            return False

        self.assertEqual(drain(self.url, work=work, cleanup=lambda _: False, lanes=1), 0)
        self.assertEqual(len(calls), 2)
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM worker_wakeup").fetchone()
            self.assertEqual(row["generation"], row["acknowledged"])
            self.assertIsNone(row["lease_until"])

    def test_default_drain_starts_four_lanes_and_waits_before_acknowledging(self):
        from minkops_platform.worker_hosting import drain

        barrier = threading.Barrier(4, timeout=5)
        lock = threading.Lock()
        started = 0

        def work(url):
            nonlocal started
            with lock:
                started += 1
                first = started <= 4
            if not first:
                return False
            barrier.wait()
            with psycopg.connect(url, row_factory=dict_row) as c:
                row = c.execute("SELECT * FROM worker_wakeup").fetchone()
                self.assertGreater(row["generation"], row["acknowledged"])
                self.assertIsNotNone(row["lease_until"])
            return True

        self.assertEqual(drain(self.url, work=work, cleanup=lambda _: False), 4)
        with psycopg.connect(self.url) as c:
            self.assertTrue(
                c.execute("SELECT generation=acknowledged FROM worker_wakeup").fetchone()[0]
            )

    def test_runner_publishes_lease_before_submitting_any_lane(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from minkops_platform.worker_hosting import drain

        testcase = self

        class ObservedPool(ThreadPoolExecutor):
            def submit(self, fn, *args, **kwargs):
                with psycopg.connect(testcase.url) as c:
                    testcase.assertIsNotNone(
                        c.execute("SELECT lease_until FROM worker_wakeup").fetchone()[0]
                    )
                return super().submit(fn, *args, **kwargs)

        with patch("minkops_platform.worker_hosting.ThreadPoolExecutor", ObservedPool):
            self.assertEqual(drain(self.url, work=lambda _: False, cleanup=lambda _: False), 0)

    def test_drain_replenishes_idle_lanes_without_waiting_for_slow_sibling(self):
        from minkops_platform.worker_hosting import drain

        slow_started, replacement_started = threading.Event(), threading.Event()
        lock = threading.Lock()
        calls = 0

        def work(url):
            nonlocal calls
            with lock:
                calls += 1
                index = calls
            if index == 1:
                slow_started.set()
                self.assertTrue(replacement_started.wait(5))
            elif index == 2:
                self.assertTrue(slow_started.wait(5))
            elif index == 3:
                replacement_started.set()
            else:
                return False
            return True

        self.assertEqual(drain(self.url, lanes=2, work=work, cleanup=lambda _: False), 3)

    def test_another_runner_exits_without_claiming_work(self):
        from minkops_platform.worker_hosting import RUNNER_LOCK, drain

        with psycopg.connect(self.url, autocommit=True) as c:
            c.execute("SELECT pg_advisory_lock(%s)", (RUNNER_LOCK,))
            self.assertEqual(drain(self.url, work=lambda _: self.fail("overlapping execution")), 0)

    def test_timeout_leaves_pending_work_for_successor(self):
        from minkops_platform.worker_hosting import drain

        self.assertEqual(drain(self.url, max_seconds=0, work=lambda _: True), 0)
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM worker_wakeup").fetchone()
            self.assertGreater(row["generation"], row["acknowledged"])
            self.assertIsNone(row["lease_until"])

    def test_lane_exception_waits_for_sibling_before_releasing_runner(self):
        from minkops_platform.worker_hosting import RUNNER_LOCK, drain

        barrier = threading.Barrier(2, timeout=5)
        lock = threading.Lock()
        calls = 0

        def work(url):
            nonlocal calls
            with lock:
                calls += 1
                index = calls
            barrier.wait()
            if index == 1:
                raise RuntimeError("lane failure")
            with psycopg.connect(url, autocommit=True) as c:
                self.assertFalse(
                    c.execute("SELECT pg_try_advisory_lock(%s)", (RUNNER_LOCK,)).fetchone()[0]
                )
            return True

        with self.assertRaisesRegex(RuntimeError, "lane failure"):
            drain(self.url, lanes=2, work=work, cleanup=lambda _: False)
        with psycopg.connect(self.url, autocommit=True) as c:
            self.assertTrue(
                c.execute("SELECT pg_try_advisory_lock(%s)", (RUNNER_LOCK,)).fetchone()[0]
            )
            c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))

    def test_wakeup_is_transactional(self):
        with psycopg.connect(self.url) as c:
            before = c.execute("SELECT generation FROM worker_wakeup").fetchone()[0]
            tenant = c.execute(
                "INSERT INTO tenants(slug,name) VALUES(gen_random_uuid()::text,'Wakeup test') RETURNING id"
            ).fetchone()[0]
            actor = c.execute(
                "INSERT INTO users(email,name,password_hash) VALUES(gen_random_uuid()::text || '@example.com','Wakeup test','unused') RETURNING id"
            ).fetchone()[0]
            task = c.execute(
                "INSERT INTO tasks(tenant_id,title) VALUES(%s,'Wakeup test') RETURNING id",
                (tenant,),
            ).fetchone()[0]
            c.execute(
                "INSERT INTO workflows(tenant_id,key,name) VALUES(%s,'source-discovery','Wakeup test')",
                (tenant,),
            )
            c.execute(
                """INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
                   definition_version,request_key,request_hash,config,file_ids)
                   VALUES(%s,%s,%s,'source-discovery','0.6.0',gen_random_uuid(),
                          'test','{}','[]')""",
                (tenant, task, actor),
            )
            self.assertEqual(
                c.execute("SELECT generation FROM worker_wakeup").fetchone()[0], before + 1
            )
            c.rollback()
            self.assertEqual(
                c.execute("SELECT generation FROM worker_wakeup").fetchone()[0], before
            )
