"""Active-time limits use real task/run locks and existing Stop semantics."""
import unittest
from unittest.mock import patch

import psycopg
import test_accounts_api as accounts
from psycopg.rows import dict_row

URL=accounts.URL


@unittest.skipUnless(URL,'TEST_DATABASE_URL is required')
class RunLimitTests(unittest.TestCase):
    setUp=accounts.AccountsTests.setUp
    launch=accounts.AccountsTests.launch

    def clock(self,c,task):
        return c.execute('SELECT * FROM tasks WHERE id=%s',(task,)).fetchone()

    def test_queue_review_pause_and_parallel_children_use_one_clock(self):
        from minkops_platform.run_controls import task_control
        run,_=self.launch()
        with psycopg.connect(URL,row_factory=dict_row) as c:
            self.assertIsNone(self.clock(c,run['task_id'])['processing_started_at'])
            c.execute("UPDATE workflow_runs SET state='executing' WHERE id=%s",(run['id'],))
            started=self.clock(c,run['task_id'])['processing_started_at']
            self.assertIsNotNone(started)
            c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-interval '3 minutes' WHERE id=%s",(run['task_id'],))
            actor=c.execute('SELECT actor_id FROM workflow_runs WHERE id=%s',(run['id'],)).fetchone()['actor_id']
            task_control(c,run['tenant_id'],{'id':actor},run['task_id'],'pause')
            paused=self.clock(c,run['task_id'])
            self.assertIsNone(paused['processing_started_at'])
            self.assertAlmostEqual(paused['processing_seconds'],180,delta=2)
            task_control(c,run['tenant_id'],{'id':actor},run['task_id'],'resume')
            self.assertIsNotNone(self.clock(c,run['task_id'])['processing_started_at'])
            c.execute("UPDATE workflow_runs SET state='review' WHERE id=%s",(run['id'],))
            self.assertIsNone(self.clock(c,run['task_id'])['processing_started_at'])
            # A batch parent's aggregation state is not processing by itself.
            c.execute("UPDATE workflow_runs SET config=config || '{\"batch\":true}',state='executing' WHERE id=%s",(run['id'],))
            self.assertIsNone(self.clock(c,run['task_id'])['processing_started_at'])
            c.execute("UPDATE workflow_runs SET config=config-'batch' WHERE id=%s",(run['id'],))
            first=self.clock(c,run['task_id'])['processing_started_at']
            from minkops_platform.accounts.batch import create_child
            parent=c.execute('SELECT * FROM workflow_runs WHERE id=%s',(run['id'],)).fetchone()
            child=create_child(c,parent,self.file_id)
            c.execute("UPDATE workflow_runs SET state='executing' WHERE id=%s",(child['id'],))
            self.assertEqual(self.clock(c,run['task_id'])['processing_started_at'],first)
            c.execute("UPDATE workflow_runs SET state='completed' WHERE id=%s",(run['id'],))
            self.assertEqual(self.clock(c,run['task_id'])['processing_started_at'],first)
            c.execute("UPDATE workflow_runs SET state='review' WHERE id=%s",(child['id'],))
            self.assertIsNone(self.clock(c,run['task_id'])['processing_started_at'])

    def test_timeout_preserves_output_ids_and_cancel_intent_without_operator_attribution(self):
        from psycopg.types.json import Jsonb

        from minkops_platform.run_limits import expire
        run,_=self.launch()
        raw={'records':[],'checkpoint':'already stored'}
        with psycopg.connect(URL,row_factory=dict_row) as c:
            c.execute("UPDATE workflow_runs SET state='executing',session_id='limit-session',turn_id='limit-turn',result=%s WHERE id=%s",(Jsonb(raw),run['id']))
            c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-interval '46 minutes' WHERE id=%s",(run['task_id'],))
            self.assertGreaterEqual(expire(c),1)
            task=self.clock(c,run['task_id'])
            self.assertEqual((task['control_state'],task['stop_reason']),('stopped','time_limit'))
            self.assertIsNone(task['processing_started_at'])
            stopped=c.execute('SELECT * FROM workflow_runs WHERE id=%s',(run['id'],)).fetchone()
            self.assertEqual(stopped['result'],raw)
            self.assertEqual(stopped['session_id'],'limit-session')
            self.assertTrue(stopped['config']['timeout_cancel_pending'])
            event=c.execute("SELECT payload FROM event_outbox WHERE aggregate_id=%s AND event_type='task.control.stop' ORDER BY id DESC LIMIT 1",(run['task_id'],)).fetchone()
            self.assertIsNone(event['payload']['actor_id'])
            self.assertEqual(event['payload']['reason'],'time_limit')
            self.assertEqual(expire(c),0)

    def test_configured_cap_and_review_wait_are_separate_from_wall_time(self):
        from minkops_platform.run_limits import expire
        run,_=self.launch()
        with psycopg.connect(URL,row_factory=dict_row) as c:
            c.execute("UPDATE tasks SET created_at=now()-interval '2 days',updated_at=now()-interval '2 days' WHERE id=%s",(run['task_id'],))
            self.assertEqual(expire(c),0)
            c.execute("UPDATE workflow_runs SET state='executing' WHERE id=%s",(run['id'],))
            c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-interval '2 minutes' WHERE id=%s",(run['task_id'],))
            with patch.dict('os.environ',{'MINKOPS_RUN_TIMEOUT_MINUTES':'1'}):
                self.assertGreaterEqual(expire(c),1)

    def test_silent_provider_cancellation_retries_after_committed_stop(self):
        from minkops_platform.run_limits import enforce
        run,_=self.launch()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE workflow_runs SET state='executing',session_id='silent-session',turn_id='silent-turn' WHERE id=%s",(run['id'],))
            c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-interval '46 minutes' WHERE id=%s",(run['task_id'],))
        with patch('minkops_platform.runtime.openai_hosted.cancel_turn',side_effect=TimeoutError) as cancel:
            enforce(URL)
            cancel.assert_called_once_with('silent-session','silent-turn')
        with psycopg.connect(URL,row_factory=dict_row) as c:
            self.assertEqual(self.clock(c,run['task_id'])['control_state'],'stopped')
            self.assertTrue(c.execute('SELECT config FROM workflow_runs WHERE id=%s',(run['id'],)).fetchone()['config']['timeout_cancel_pending'])
        with patch('minkops_platform.runtime.openai_hosted.cancel_turn') as cancel:
            enforce(URL)
            cancel.assert_called_once_with('silent-session','silent-turn')
        with psycopg.connect(URL,row_factory=dict_row) as c:
            self.assertFalse(c.execute('SELECT config FROM workflow_runs WHERE id=%s',(run['id'],)).fetchone()['config']['timeout_cancel_pending'])

    def test_busy_task_does_not_break_unrelated_requests_and_is_retried(self):
        from minkops_platform.run_limits import expire
        run,_=self.launch()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE workflow_runs SET state='executing' WHERE id=%s",(run['id'],))
            c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-interval '46 minutes' WHERE id=%s",(run['task_id'],))
        with psycopg.connect(URL) as held, psycopg.connect(URL,row_factory=dict_row) as c:
            held.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f"control:{run['task_id']}",))
            c.execute("SET LOCAL lock_timeout='50ms'")
            expire(c)
            self.assertEqual(self.clock(c,run['task_id'])['control_state'],'active')
        # A failing request still commits the automatic stop before auth work.
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)
        with psycopg.connect(URL,row_factory=dict_row) as c:
            self.assertEqual(self.clock(c,run['task_id'])['control_state'],'stopped')
