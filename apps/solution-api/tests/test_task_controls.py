"""Run controls are durable, tenant scoped and fence subsequent dispatch."""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import test_desktop
from fastapi.testclient import TestClient

from minkops_api.main import app

URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class TaskControlTests(unittest.TestCase):
    setUp = test_desktop.DesktopTests.setUp
    pair = test_desktop.DesktopTests.pair
    launch = test_desktop.DesktopTests.launch

    def control(self, task_id, action):
        return self.client.post(f"/api/tenants/{self.slug}/tasks/{task_id}/control",
                                headers=self.csrf, json={"action": action})

    def test_native_only_timeout_retains_late_receipt_and_blocks_new_claims(self):
        self.pair()
        job,_=self.launch()
        claim=self.client.post(self.worker_base+'/claim',headers=self.worker,json={}).json()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-interval '46 minutes' WHERE id=%s",(job['task_id'],))
        task=self.client.get(f"/api/tenants/{self.slug}/tasks/{job['task_id']}").json()
        self.assertEqual(task['status'],'stopped')
        self.assertIn('45 minutes of active processing',task['summary'])
        receipt={'claim_token':claim['claim_token'],'result':{'available':True,'companies':['Office']}}
        done=self.client.post(self.worker_base+f"/jobs/{job['id']}/finish",headers=self.worker,json=receipt)
        self.assertEqual(done.status_code,200,done.text)
        self.assertEqual(done.json()['result'],receipt['result'])
        self.assertIsNone(self.client.post(self.worker_base+'/claim',headers=self.worker,json={}).json())
        self.assertEqual(self.client.get(f"/api/tenants/{self.slug}/tasks/{job['task_id']}").json()['status'],'stopped')

    def test_pause_resume_stop_and_duplicate_requests_are_audited_once(self):
        self.pair()
        job, _ = self.launch()
        task_id = job["task_id"]
        for _ in range(2):
            response = self.control(task_id, "pause")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["control_state"], "paused")
        self.assertIsNone(self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json())
        with psycopg.connect(URL) as connection:
            generation = connection.execute("SELECT generation FROM worker_wakeup").fetchone()[0]
        self.assertEqual(self.control(task_id, "resume").status_code, 200)
        with psycopg.connect(URL) as connection:
            self.assertEqual(connection.execute("SELECT generation FROM worker_wakeup").fetchone()[0], generation + 1)
        claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        self.assertEqual(claim["id"], job["id"])
        self.assertEqual(self.control(task_id, "stop").status_code, 200)
        self.assertEqual(self.control(task_id, "resume").status_code, 409)
        # An operation underway can finish; that observation must not resurrect it.
        done = self.client.post(self.worker_base + f"/jobs/{job['id']}/finish", headers=self.worker,
                                json={"claim_token": claim["claim_token"],
                                      "result": {"available": True, "companies": ["Office"]}})
        self.assertEqual(done.status_code, 200, done.text)
        task = self.client.get(f"/api/tenants/{self.slug}/tasks/{task_id}").json()
        self.assertEqual(task["status"], "stopped")
        self.assertEqual([e["event_type"] for e in task["events"] if e["event_type"].startswith("control.")],
                         ["control.pause", "control.resume", "control.stop"])
        with psycopg.connect(URL) as connection:
            events = connection.execute("SELECT payload FROM event_outbox WHERE aggregate_id=%s AND event_type LIKE 'task.control.%%'",
                                        (task_id,)).fetchall()
            self.assertEqual(len(events), 3)
            self.assertTrue(all(e[0]["actor_id"] for e in events))

    def test_terminal_tasks_invalid_actions_and_csrf_are_rejected(self):
        self.pair()
        job, _ = self.launch()
        task_id = job["task_id"]
        self.assertEqual(self.control(task_id, "restart").status_code, 422)
        route = f"/api/tenants/{self.slug}/tasks/{task_id}/control"
        self.assertEqual(self.client.post(route, json={"action": "stop"}).status_code, 403)
        with psycopg.connect(URL) as connection:
            connection.execute("UPDATE tasks SET status='completed' WHERE id=%s", (task_id,))
        self.assertEqual(self.control(task_id, "pause").status_code, 409)

    def test_other_members_and_other_tenants_cannot_control_the_operators_task(self):
        self.pair()
        job, _ = self.launch()
        with psycopg.connect(URL) as connection:
            other = connection.execute("SELECT id FROM users WHERE id<>%s LIMIT 1", (self.user["id"],)).fetchone()[0]
            connection.execute("UPDATE desktop_jobs SET actor_id=%s WHERE id=%s", (other, job["id"]))
        self.assertEqual(self.control(job["task_id"], "stop").status_code, 403)
        self.assertEqual(self.client.post(f"/api/tenants/{self.slug}/tasks/{uuid.uuid4()}/control", headers=self.csrf, json={"action": "stop"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/tenants/pr-infra/tasks/{job['task_id']}/control", headers=self.csrf, json={"action": "stop"}).status_code, 403)

    def test_concurrent_duplicate_pause_is_one_durable_transition(self):
        self.pair()
        job, _ = self.launch()
        route = f"/api/tenants/{self.slug}/tasks/{job['task_id']}/control"
        def pause(_):
            with TestClient(app) as client:
                client.cookies.update(self.client.cookies)
                return client.post(route, headers=self.csrf, json={"action": "pause"}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(pause, range(2))), [200, 200])
        task = self.client.get(route.removesuffix("/control")).json()
        self.assertEqual(sum(e["event_type"] == "control.pause" for e in task["events"]), 1)
