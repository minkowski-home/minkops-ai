"""Cheap recovery checks dispatch only eligible work, never idle paid jobs."""
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from db.testing import disposable_database


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is required')
class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        context = disposable_database(os.environ['TEST_DATABASE_URL'])
        self.url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.calls = []

    def run_row(self, config=None):
        with psycopg.connect(self.url) as c:
            tenant = c.execute("INSERT INTO tenants(slug,name) VALUES(%s,'Recovery') RETURNING id", (uuid4().hex,)).fetchone()[0]
            actor = c.execute("INSERT INTO users(email,name,password_hash) VALUES(%s,'Recovery','unused') RETURNING id",
                              (uuid4().hex+'@example.com',)).fetchone()[0]
            task = c.execute("INSERT INTO tasks(tenant_id,title) VALUES(%s,'Recovery') RETURNING id", (tenant,)).fetchone()[0]
            c.execute("INSERT INTO workflows(tenant_id,key,name) VALUES(%s,'source-discovery','Recovery')", (tenant,))
            return c.execute("""INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
                definition_version,request_key,request_hash,config,file_ids)
                VALUES(%s,%s,%s,'source-discovery','1',%s,'test',%s,'[]') RETURNING id""",
                (tenant,task,actor,uuid4(),Jsonb(config or {}))).fetchone()[0]

    def recover(self):
        from minkops_platform.worker_hosting import recover
        return recover(self.url, lambda: self.calls.append(True))

    def test_idle_even_with_old_notification_does_not_start_job(self):
        with psycopg.connect(self.url) as c:
            c.execute('UPDATE worker_wakeup SET generation=generation+1')
        self.assertFalse(self.recover())
        self.assertEqual(self.calls, [])

    def test_missing_notification_is_recovered_and_duplicate_check_is_coalesced(self):
        self.run_row()
        with psycopg.connect(self.url) as c:
            c.execute('UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL')
        self.assertTrue(self.recover())
        self.assertFalse(self.recover())
        self.assertEqual(len(self.calls), 1)

    def test_a_run_item_whose_wake_up_was_lost_is_recovered_but_a_waiting_one_is_not(self):
        import factory
        from psycopg.rows import dict_row

        from minkops_platform import work
        blocker = {'kind': 'sync', 'ref': 'pc-1'}
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            tenant = factory.tenant(c)
            factory.run(c, tenant, factory.client(c, tenant), factory.workflow(c, tenant), factory.user(c, tenant),
                        [work.ItemSpec('bill', {'file_id': 'a'}, waiting_on=blocker)])
            c.execute('UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL')
        self.assertFalse(self.recover())
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            work.release(c, tenant['id'], blocker)
            # The release's notification and dispatch were lost.
            c.execute('UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL')
        self.assertTrue(self.recover())
        self.assertEqual(len(self.calls), 1)

    def test_blocked_and_stopped_work_is_not_runnable(self):
        run = self.run_row({'awaits': {'profile': str(uuid4())}})
        self.assertFalse(self.recover())
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE tasks SET control_state='stopped' WHERE id=(SELECT task_id FROM workflow_runs WHERE id=%s)", (run,))
            c.execute("UPDATE workflow_runs SET config=config-'awaits' WHERE id=%s", (run,))
        self.assertFalse(self.recover())

    def test_live_runner_is_not_disturbed(self):
        from minkops_platform.worker_hosting import RUNNER_LOCK
        self.run_row()
        with psycopg.connect(self.url, autocommit=True) as c:
            c.execute('SELECT pg_advisory_lock(%s)', (RUNNER_LOCK,))
            self.assertFalse(self.recover())
        self.assertEqual(self.calls, [])

    def test_batch_waiting_for_a_decision_does_not_start_idle_jobs(self):
        parent = self.run_row({'batch': True})
        with psycopg.connect(self.url) as c:
            child = c.execute("""INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
                definition_version,request_key,request_hash,config,file_ids,parent_run_id)
                SELECT tenant_id,task_id,actor_id,workflow_key,definition_version,%s,'child',%s,'[]',id
                FROM workflow_runs WHERE id=%s RETURNING id""",
                (uuid4(), Jsonb({'awaits': {'profile': str(uuid4())}}), parent)).fetchone()[0]
        self.assertFalse(self.recover())
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE workflow_runs SET state='review',updated_at=clock_timestamp() WHERE id=%s", (child,))
        self.assertTrue(self.recover(), 'A terminal unaggregated child needs reconciliation')

    def test_stale_start_lease_recovers_but_fresh_start_lease_waits(self):
        self.run_row()
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes'")
        self.assertFalse(self.recover())
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '27 minutes'")
        self.assertTrue(self.recover())

    def test_terminal_session_cleanup_can_wake_maintenance(self):
        run = self.run_row()
        with psycopg.connect(self.url) as c:
            c.execute("UPDATE workflow_runs SET state='review',session_id='recoverable-session' WHERE id=%s", (run,))
            c.execute('UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL')
        self.assertTrue(self.recover())
