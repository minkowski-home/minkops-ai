"""Active-time limits stop a task through its runs' own Stop, using the real task and run locks."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from minkops_api.main import app
from minkops_platform import work
from minkops_platform.run_controls import task_control
from minkops_platform.run_limits import expire

URL = os.environ.get("TEST_DATABASE_URL")
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform/tests"))


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class RunLimitTests(unittest.TestCase):
    def setUp(self):
        import factory
        with factory.connect() as db:
            tenant = factory.tenant(db)
            self.actor = factory.user(db, tenant, role="admin")
            self.run = factory.run(db, tenant, factory.client(db, tenant), factory.workflow(db, tenant), self.actor,
                                   [work.ItemSpec("bill", {"file_id": "a"}), work.ItemSpec("bill", {"file_id": "b"})],
                                   handler="desk.bill")
            first = db.execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal LIMIT 1",
                               (self.run["id"],)).fetchone()
            work.add_records(db, first, [{"kind": "bill", "source": {"file_id": "a", "bill": 1},
                                          "facts": {"file": "a.pdf", "bill": 1}}])
            db.commit()
        self.tenant, self.task = tenant, self.run["task_id"]

    def clock(self, c):
        return c.execute("SELECT * FROM tasks WHERE id=%s", (self.task,)).fetchone()

    def start(self, c, *, minutes_ago):
        """One item is being worked, and has been for this long."""
        item = work.claim(c, tenant_id=self.tenant["id"])
        c.execute("UPDATE tasks SET processing_started_at=clock_timestamp()-make_interval(mins=>%s) WHERE id=%s",
                  (minutes_ago, self.task))
        c.commit()
        return item

    def test_only_a_worked_item_counts_toward_the_budget_and_a_pause_keeps_what_it_used(self):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            self.assertIsNone(self.clock(c)["processing_started_at"])
            item = self.start(c, minutes_ago=3)
            task_control(c, self.tenant["id"], self.actor, self.task, "pause")
            paused = self.clock(c)
            self.assertIsNone(paused["processing_started_at"])
            self.assertAlmostEqual(paused["processing_seconds"], 180, delta=2)
            task_control(c, self.tenant["id"], self.actor, self.task, "resume")
            self.assertIsNotNone(self.clock(c)["processing_started_at"])
            # A finished item stops the clock: waiting for review costs no budget.
            work.finish(c, item["id"], item["lease_token"], "done")
            self.assertIsNone(self.clock(c)["processing_started_at"])

    def test_a_task_past_its_budget_stops_like_an_operator_stop_and_says_why(self):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            self.start(c, minutes_ago=46)
            self.assertGreaterEqual(expire(c), 1)
            task = self.clock(c)
            self.assertEqual((task["control_state"], task["stop_reason"]), ("stopped", "time_limit"))
            self.assertIsNone(task["processing_started_at"])
            # The run's own Stop: its unstarted item is cancelled and its unsaved bill holds.
            states = [i["state"] for i in c.execute("SELECT state FROM run_items WHERE run_id=%s ORDER BY ordinal",
                                                    (self.run["id"],)).fetchall()]
            self.assertEqual(sorted(states), ["cancelled", "running"])
            record = c.execute("SELECT status, hold_codes FROM run_records WHERE run_id=%s",
                               (self.run["id"],)).fetchone()
            self.assertEqual((record["status"], record["hold_codes"]), ("held", ["run_stopped"]))
            event = c.execute("""SELECT payload FROM event_outbox WHERE aggregate_id=%s AND event_type='task.control.stop'
                                 ORDER BY id DESC LIMIT 1""", (self.task,)).fetchone()
            self.assertEqual((event["payload"]["actor_id"], event["payload"]["reason"]), (None, "time_limit"))
            self.assertEqual(expire(c), 0)

    def test_a_configured_budget_and_waiting_time_are_separate_from_wall_time(self):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute("UPDATE tasks SET created_at=now()-interval '2 days' WHERE id=%s", (self.task,))
            self.assertEqual(expire(c), 0)
            self.start(c, minutes_ago=2)
            with patch.dict("os.environ", {"MINKOPS_RUN_TIMEOUT_MINUTES": "1"}):
                self.assertGreaterEqual(expire(c), 1)
            self.assertEqual(self.clock(c)["control_state"], "stopped")

    def test_a_busy_task_is_retried_and_a_failed_request_still_commits_its_stop(self):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            self.start(c, minutes_ago=46)
        with psycopg.connect(URL) as held, psycopg.connect(URL, row_factory=dict_row) as c:
            held.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"control:{self.task}",))
            c.execute("SET LOCAL lock_timeout='50ms'")
            expire(c)
            self.assertEqual(self.clock(c)["control_state"], "active")
        # Every request commits the deadline fence before its own work, even one refused for its session.
        os.environ["DATABASE_URL"] = URL
        self.assertEqual(TestClient(app).get("/api/auth/me").status_code, 401)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            self.assertEqual(self.clock(c)["control_state"], "stopped")


if __name__ == "__main__":
    unittest.main()
