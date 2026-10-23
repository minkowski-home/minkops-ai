import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DEV_MODE", "1")
from minkops_api.main import app

ROOT = Path(__file__).resolve().parents[3]
URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "long test password 123!"


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = URL
        subprocess.run(
            [sys.executable, str(ROOT / "db" / "seed_demo.py")],
            env={**os.environ, "DATABASE_URL": URL, "DEMO_PASSWORD": PASSWORD},
            check=True, capture_output=True, text=True,
        )

    def setUp(self):
        self.client = TestClient(app)
        login = self.client.post("/api/auth/login", json={
            "email": "demo@example.com", "password": PASSWORD
        })
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.get("/api/auth/me").json()["csrf_token"]

    def test_a_workflow_installed_from_a_retired_definition_is_listed_but_not_runnable(self):
        from psycopg.types.json import Jsonb
        with psycopg.connect(URL) as c:
            c.execute("""INSERT INTO workflows(tenant_id,key,name,status,execution_binding)
                SELECT id,'source-discovery','Source discovery','active',%s FROM tenants WHERE slug='mock-tenant'
                ON CONFLICT (tenant_id,key) DO UPDATE SET execution_binding=EXCLUDED.execution_binding""",
                      (Jsonb({"definition": "accounts-desk/workflows/source-discovery", "handler": "accounts.discovery",
                              "presentation": "accounts-discovery"}),))
        try:
            workspace = self.client.get("/api/tenants/mock-tenant/workspace")
            self.assertEqual(workspace.status_code, 200, workspace.text)
            retired = next(w for w in workspace.json()["workflows"] if w["key"] == "source-discovery")
            self.assertIsNone(retired["run_schema"])
            current = next(w for w in workspace.json()["workflows"] if w["key"] == "bill-entry")
            self.assertEqual(current["presentation"], "desk-review")
            self.assertIn("company_mode", current["run_schema"]["properties"])
        finally:
            with psycopg.connect(URL) as c:
                c.execute("DELETE FROM workflows WHERE key='source-discovery' AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant')")

    def test_pr_infra_empty_and_mock_has_linked_catalog(self):
        pr = self.client.get("/api/tenants/pr-infra/workspace")
        self.assertEqual(pr.status_code, 200, pr.text)
        self.assertEqual(pr.json()["employees"], [])
        self.assertEqual(pr.json()["workflows"], [])
        mock = self.client.get("/api/tenants/mock-tenant/workspace")
        self.assertEqual(mock.status_code, 200, mock.text)
        self.assertTrue(mock.json()["employees"])
        self.assertTrue(mock.json()["workflows"])
        self.assertTrue(mock.json()["workflows"][0]["employee_ids"])

    def test_settings_are_validated_and_emit_outbox_event(self):
        workspace = self.client.get("/api/tenants/mock-tenant/workspace").json()
        employee = workspace["employees"][0]
        invalid = self.client.patch(
            f"/api/tenants/mock-tenant/employees/{employee['id']}",
            headers={"x-csrf-token": self.csrf},
            json={"config_values": {"unknown_setting": True}},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)
        properties = employee["config_schema"]["properties"]
        key = next(iter(properties))
        value = properties[key].get("enum", [True])[0]
        updated = self.client.patch(
            f"/api/tenants/mock-tenant/employees/{employee['id']}",
            headers={"x-csrf-token": self.csrf},
            json={"config_values": {key: value}},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["config_values"][key], value)
        with psycopg.connect(URL) as connection:
            self.assertGreater(connection.execute(
                "SELECT count(*) FROM event_outbox WHERE aggregate_id = %s",
                (employee["id"],),
            ).fetchone()[0], 0)

    def test_member_can_view_but_cannot_change_settings(self):
        workspace = self.client.get("/api/tenants/mock-tenant/workspace").json()
        employee = workspace["employees"][0]
        with psycopg.connect(URL) as connection:
            user_id = connection.execute(
                """INSERT INTO users (name, email, password_hash, email_verified_at)
                   VALUES ('Viewer', 'workspace-viewer@minkops.test', 'unused', now())
                   ON CONFLICT DO NOTHING RETURNING id"""
            ).fetchone()
            if user_id:
                tenant_id = connection.execute(
                    "SELECT id FROM tenants WHERE slug = 'mock-tenant'"
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO memberships (tenant_id, user_id, role) VALUES (%s, %s, 'member')",
                    (tenant_id, user_id[0]),
                )
            # A session lets this check focus on authorization, not password setup.
            member_id = connection.execute(
                "SELECT id FROM users WHERE email = 'workspace-viewer@minkops.test'"
            ).fetchone()[0]
            from minkops_api.auth import digest
            session_token = f"member-test-session-{uuid.uuid4()}"
            connection.execute(
                """INSERT INTO sessions (user_id, token_hash, expires_at)
                   VALUES (%s, %s, now() + interval '1 hour')
                   ON CONFLICT (token_hash) DO NOTHING""",
                (member_id, digest(session_token)),
            )
        viewer = TestClient(app)
        viewer.cookies.set("minkops_session", session_token)
        self.assertEqual(viewer.get("/api/tenants/mock-tenant/workspace").status_code, 200)
        csrf = viewer.get("/api/auth/me").json()["csrf_token"]
        self.assertEqual(viewer.patch(
            f"/api/tenants/mock-tenant/employees/{employee['id']}",
            headers={"x-csrf-token": csrf},
            json={"config_values": {}},
        ).status_code, 403)

    def test_task_detail_has_visual_progress_events(self):
        # The test owns its task; the demo seed no longer fabricates activity.
        with psycopg.connect(URL) as connection:
            tenant_id, workflow_id = connection.execute(
                """SELECT t.id, w.id FROM tenants t JOIN workflows w ON w.tenant_id = t.id
                   WHERE t.slug = 'mock-tenant' AND w.key = 'bill-entry'"""
            ).fetchone()
            task_id = connection.execute(
                """INSERT INTO tasks (tenant_id, workflow_id, title, status, progress, summary)
                   VALUES (%s, %s, 'Progress fixture', 'running', 40, 'Reading bills.')
                   RETURNING id""",
                (tenant_id, workflow_id),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO task_events (tenant_id, task_id, event_type, summary, progress)
                   VALUES (%s, %s, 'executing', 'Reading bills.', 40)""",
                (tenant_id, task_id),
            )
        workspace = self.client.get("/api/tenants/mock-tenant/workspace").json()
        task = next(t for t in workspace["tasks"] if t["id"] == str(task_id))
        detail = self.client.get(f"/api/tenants/mock-tenant/tasks/{task['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertTrue(detail.json()["events"])
        self.assertEqual(detail.json()["id"], task["id"])
        self.assertEqual(self.client.get(
            f"/api/tenants/pr-infra/tasks/{task['id']}"
        ).status_code, 404)



@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class ClientTaskTests(unittest.TestCase):
    """A run's task belongs to its client: reaching it by its ID needs that client too."""

    def setUp(self):
        from psycopg.rows import dict_row
        from pwdlib import PasswordHash
        sys.path.insert(0, str(ROOT / "platform/tests"))
        import factory

        from minkops_platform import work
        os.environ["DATABASE_URL"] = URL
        with psycopg.connect(URL, row_factory=dict_row) as db:
            self.tenant = factory.tenant(db, scoping=True)
            self.member = factory.user(db, self.tenant)
            db.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                       (PasswordHash.recommended().hash(PASSWORD), self.member["id"]))
            granted, other = factory.client(db, self.tenant), factory.client(db, self.tenant)
            db.execute("INSERT INTO client_access(tenant_id,client_id,user_id) VALUES (%s,%s,%s)",
                       (self.tenant["id"], granted["id"], self.member["id"]))
            flow = factory.workflow(db, self.tenant)
            factory.assign(db, self.tenant, self.member, flow)
            self.runs = {client["slug"]: factory.run(db, self.tenant, client, flow, self.member,
                                                     [work.ItemSpec("bill", {"file_id": "a"})])
                         for client in (granted, other)}
            self.granted, self.other = granted["slug"], other["slug"]

    def test_a_task_of_a_client_the_member_cannot_reach_is_not_found_by_its_id(self):
        client = TestClient(app)
        self.assertEqual(client.post("/api/auth/login", json={"email": self.member["email"], "password": PASSWORD})
                         .status_code, 200)
        csrf = {"x-csrf-token": client.get("/api/auth/me").json()["csrf_token"]}
        base = f"/api/tenants/{self.tenant['slug']}/tasks"
        mine, theirs = self.runs[self.granted], self.runs[self.other]
        # A run's task names its run and client, so its page can show the run's review.
        detail = client.get(f"{base}/{mine['task_id']}").json()
        self.assertEqual(detail["run"], {"id": str(mine["id"]), "client": self.granted})
        self.assertEqual(client.get(f"{base}/{theirs['task_id']}").status_code, 404)
        self.assertEqual(client.post(f"{base}/{theirs['task_id']}/control", json={"action": "pause"},
                                     headers=csrf).status_code, 404)


if __name__ == "__main__":
    unittest.main()
