"""Attention over HTTP: items by client access, an audited Done, and questions answered once per member."""

import os
import sys
import unittest
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from pwdlib import PasswordHash

from minkops_api.main import app
from minkops_platform import attention, profiles, work
from minkops_platform.accounts import statement_layouts

URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "long test password 123!"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform/tests"))


@unittest.skipUnless(URL, "TEST_DATABASE_URL required")
class AttentionApiTests(unittest.TestCase):
    def setUp(self):
        import factory
        os.environ["DATABASE_URL"] = URL
        hashed = PasswordHash.recommended().hash(PASSWORD)
        with psycopg.connect(URL, row_factory=dict_row) as db:
            self.tenant = factory.tenant(db, scoping=True)
            self.admin = factory.user(db, self.tenant, role="admin")
            self.member = factory.user(db, self.tenant)
            db.execute("UPDATE users SET password_hash=%s WHERE id = ANY(%s)",
                       (hashed, [self.admin["id"], self.member["id"]]))
            granted, other = factory.client(db, self.tenant), factory.client(db, self.tenant)
            db.execute("INSERT INTO client_access(tenant_id,client_id,user_id) VALUES (%s,%s,%s)",
                       (self.tenant["id"], granted["id"], self.member["id"]))
            flow = factory.workflow(db, self.tenant, key="statement-entry")
            self.items = {}
            for client in (granted, other):
                run = factory.run(db, self.tenant, client, flow, self.admin, [work.ItemSpec("chunk", {"file_id": "a"})],
                                  handler="desk.statement")
                gap = attention.record(db, run, f"gap:{run['id']}", "ICICI Current A/c", "Transactions missing",
                                       target={"reason": "A statement for 1–14 September is missing."})
                profile = profiles.create(db, self.tenant["id"], statement_layouts.KIND, f"sig-{client['slug']}", {
                    "columns": {"date": {"column": 1, "order": "dmy"}}, "question": "date_order"},
                    status="proposed", actor=self.admin["id"], provenance={})
                question = statement_layouts.ask(db, run, profile, "icici.csv", "date_order", {"samples": []},
                                                 ["01/02/2026"])
                self.items[client["slug"]] = {"gap": gap, "question": question, "profile": profile}
            self.granted, self.other = granted["slug"], other["slug"]

    def login(self, user):
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return client, {"x-csrf-token": client.get("/api/auth/me").json()["csrf_token"]}

    @property
    def base(self):
        return f"/api/tenants/{self.tenant['slug']}/attention"

    def test_members_see_only_their_clients_items_and_a_done_is_audited(self):
        member, csrf = self.login(self.member)
        listed = member.get(self.base).json()
        mine = self.items[self.granted]
        self.assertEqual({item["id"] for item in listed}, {str(mine["gap"]["id"]), str(mine["question"]["id"])})
        question = next(item for item in listed if item["kind"] == "layout")
        # The server owns each card's answers and their labels.
        self.assertEqual((question["label"], question["question"]["options"]), ("Choose date order", [
            {"action": "dmy", "label": "Day first"}, {"action": "mdy", "label": "Month first"}]))
        self.assertEqual(next(item for item in listed if item["kind"] == "manual")["reason"],
                         "A statement for 1–14 September is missing.")
        admin, _ = self.login(self.admin)
        self.assertEqual(len(admin.get(self.base).json()), 4)
        self.assertEqual(member.post(f"{self.base}/{mine['gap']['id']}/done", headers=csrf).json(), {"status": "done"})
        with psycopg.connect(URL, row_factory=dict_row) as db:
            event = db.execute("SELECT actor_id, action FROM attention_events WHERE item_id=%s ORDER BY id DESC LIMIT 1",
                               (mine["gap"]["id"],)).fetchone()
        self.assertEqual((event["actor_id"], event["action"]), (self.member["id"], "manual_done"))
        self.assertEqual([item["kind"] for item in member.get(self.base).json()], ["layout"])

    def test_a_question_is_answered_once_per_member_and_a_replay_returns_its_receipt(self):
        admin, csrf = self.login(self.admin)
        mine = self.items[self.granted]
        url = f"{self.base}/{mine['question']['id']}/decision"
        self.assertEqual(admin.post(url, headers=csrf, json={"action": "ymd"}).status_code, 422)
        answered = admin.post(url, headers=csrf, json={"action": "mdy"})
        self.assertEqual(answered.status_code, 200, answered.text)
        self.assertEqual((answered.json()["action"], answered.json()["status"]), ("mdy", "active"))
        # A lost response is answered again from the receipt; another answer is a conflict.
        self.assertEqual(admin.post(url, headers=csrf, json={"action": "mdy"}).json(), answered.json())
        self.assertEqual(admin.get(url).json(), answered.json())
        self.assertEqual(admin.post(url, headers=csrf, json={"action": "dmy"}).status_code, 409)
        with psycopg.connect(URL, row_factory=dict_row) as db:
            profile = profiles.get(db, self.tenant["id"], mine["profile"]["id"])
        self.assertEqual((profile["status"], profile["payload"]["columns"]["date"]["order"]), ("active", "mdy"))
        # Only a question takes an answer.
        gap = admin.post(f"{self.base}/{mine['gap']['id']}/decision", headers=csrf, json={"action": "dmy"})
        self.assertEqual(gap.status_code, 409)


if __name__ == "__main__":
    unittest.main()
