"""Durable wake-ups survive dispatch failure and never acknowledge newer work."""

import os
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

        self.assertEqual(drain(self.url, work=work, cleanup=lambda _: False), 0)
        self.assertEqual(len(calls), 2)
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM worker_wakeup").fetchone()
            self.assertEqual(row["generation"], row["acknowledged"])
            self.assertIsNone(row["lease_until"])

    def test_another_runner_exits_without_claiming_work(self):
        from minkops_platform.worker_hosting import drain, RUNNER_LOCK

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

    def test_wakeup_is_transactional(self):
        with psycopg.connect(self.url) as c:
            before = c.execute("SELECT generation FROM worker_wakeup").fetchone()[0]
            tenant = c.execute("INSERT INTO tenants(slug,name) VALUES(gen_random_uuid()::text,'Wakeup test') RETURNING id").fetchone()[0]
            actor = c.execute("INSERT INTO users(email,name,password_hash) VALUES(gen_random_uuid()::text || '@example.com','Wakeup test','unused') RETURNING id").fetchone()[0]
            task = c.execute("INSERT INTO tasks(tenant_id,title) VALUES(%s,'Wakeup test') RETURNING id", (tenant,)).fetchone()[0]
            c.execute("INSERT INTO workflows(tenant_id,key,name) VALUES(%s,'source-discovery','Wakeup test')", (tenant,))
            c.execute(
                """INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
                   definition_version,request_key,request_hash,config,file_ids)
                   VALUES(%s,%s,%s,'source-discovery','0.6.0',gen_random_uuid(),
                          'test','{}','[]')""", (tenant, task, actor),
            )
            self.assertEqual(c.execute("SELECT generation FROM worker_wakeup").fetchone()[0], before + 1)
            c.rollback()
            self.assertEqual(
                c.execute("SELECT generation FROM worker_wakeup").fetchone()[0], before
            )
