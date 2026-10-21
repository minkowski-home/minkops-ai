"""Run status, record pages and idempotent decisions over per-client access."""

import os
import sys
import unittest
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from pwdlib import PasswordHash

from minkops_api.main import app
from minkops_platform import work
from minkops_platform.errors import ServiceError

URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "long test password 123!"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform/tests"))


class Handler:
    """The smallest workflow handler: Do nothing defers a record."""

    def summarize(self, run, record):
        return {"id": str(record["id"]), "status": record["status"], "version": record["version"]}

    def detail(self, connection, run, record):
        return {**self.summarize(run, record), "hold_codes": record["hold_codes"]}

    def decide(self, connection, run, record, action, detail, context):
        if action != "nothing":
            raise ServiceError("invalid", "Choose an offered action.")
        work.update_record(connection, record, status="deferred")
        work.refresh(connection, run["tenant_id"], run["id"])
        return {"status": "deferred", "version": record["version"]}


HANDLER = Handler()


@unittest.skipUnless(URL, "TEST_DATABASE_URL required")
class RunsApiTests(unittest.TestCase):
    def setUp(self):
        import factory
        os.environ["DATABASE_URL"] = URL
        work.HANDLER_MODULES["desk.test"] = __name__
        self.addCleanup(work.HANDLER_MODULES.pop, "desk.test")
        hashed = PasswordHash.recommended().hash(PASSWORD)
        with psycopg.connect(URL, row_factory=dict_row) as db:
            self.tenant = factory.tenant(db, scoping=True)
            self.admin = factory.user(db, self.tenant, role="admin")
            self.member = factory.user(db, self.tenant)
            db.execute("UPDATE users SET password_hash=%s WHERE id = ANY(%s)", (hashed, [self.admin["id"], self.member["id"]]))
            self.granted, self.other = factory.client(db, self.tenant), factory.client(db, self.tenant)
            db.execute("INSERT INTO client_access(tenant_id,client_id,user_id) VALUES (%s,%s,%s)",
                       (self.tenant["id"], self.granted["id"], self.member["id"]))
            flow = factory.workflow(db, self.tenant)
            self.runs = {}
            for client in (self.granted, self.other):
                run = factory.run(db, self.tenant, client, flow, self.admin, [work.ItemSpec("bill", {"file_id": "a"})])
                item = db.execute("SELECT * FROM run_items WHERE run_id=%s", (run["id"],)).fetchone()
                (record,) = work.add_records(db, item, [{"kind": "bill", "source": {"file_id": "a"}, "status": "held",
                                                         "hold_codes": ["supplier_missing"]}])
                self.runs[client["slug"]] = (run, record)

    def login(self, user):
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return client, {"x-csrf-token": client.get("/api/auth/me").json()["csrf_token"]}

    def base(self, client_slug):
        return f"/api/tenants/{self.tenant['slug']}/clients/{client_slug}"

    def test_members_reach_only_granted_clients_and_their_work(self):
        client, _ = self.login(self.member)
        listed = client.get(f"/api/tenants/{self.tenant['slug']}/clients").json()
        self.assertEqual([c["slug"] for c in listed], [self.granted["slug"]])
        workspace = client.get(f"/api/tenants/{self.tenant['slug']}/workspace").json()
        self.assertEqual({t["id"] for t in workspace["tasks"]}, {str(self.runs[self.granted["slug"]][0]["task_id"])})
        run, _ = self.runs[self.other["slug"]]
        self.assertEqual(client.get(self.base(self.other["slug"]) + f"/runs/{run['id']}/status").status_code, 403)

    def test_a_run_is_reachable_only_under_its_own_client(self):
        client, _ = self.login(self.admin)
        run, _ = self.runs[self.granted["slug"]]
        self.assertEqual(client.get(self.base(self.granted["slug"]) + f"/runs/{run['id']}/status").status_code, 200)
        self.assertEqual(client.get(self.base(self.other["slug"]) + f"/runs/{run['id']}/status").status_code, 404)

    def test_status_is_small_and_an_unchanged_poll_is_smaller(self):
        client, _ = self.login(self.member)
        run, _ = self.runs[self.granted["slug"]]
        route = self.base(self.granted["slug"]) + f"/runs/{run['id']}/status"
        status = client.get(route).json()
        self.assertEqual(status["records"]["held"], 1)
        self.assertEqual(client.get(route, params={"since": status["activity"]}).json(),
                         {"unchanged": True, "activity": status["activity"]})
        page = client.get(self.base(self.granted["slug"]) + f"/runs/{run['id']}/records").json()
        self.assertEqual([r["status"] for r in page["records"]], ["held"])

    def test_a_repeated_decision_returns_its_receipt_and_a_conflicting_one_gets_the_winner(self):
        client, csrf = self.login(self.member)
        _, record = self.runs[self.granted["slug"]]
        route = self.base(self.granted["slug"]) + f"/records/{record['id']}/decisions"
        body = {"action": "nothing", "version": record["version"]}
        first = client.post(route, headers=csrf, json=body)
        again = client.post(route, headers=csrf, json=body)
        self.assertEqual((first.status_code, again.status_code), (200, 200), first.text)
        self.assertEqual((first.json()["replayed"], again.json()["replayed"]), (False, True))
        admin, admin_csrf = self.login(self.admin)
        conflict = admin.post(route, headers=admin_csrf, json=body)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"]["receipt"]["status"], "deferred")
        self.assertEqual(client.post(route, json=body).status_code, 403)  # No CSRF token.
