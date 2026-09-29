import os
import sys
import unittest
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DEV_MODE", "1")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "db"))

from seed_demo import seed_demo  # noqa: E402
from main import app  # noqa: E402


URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "long test password 123!"


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = URL
        seed_demo(URL, PASSWORD)

    def setUp(self):
        self.client = TestClient(app)
        login = self.client.post("/api/auth/login", json={
            "email": "demo@example.com", "password": PASSWORD
        })
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.get("/api/auth/me").json()["csrf_token"]

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
            from auth import digest
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
        workspace = self.client.get("/api/tenants/mock-tenant/workspace").json()
        task = workspace["tasks"][0]
        detail = self.client.get(f"/api/tenants/mock-tenant/tasks/{task['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertTrue(detail.json()["events"])
        self.assertEqual(detail.json()["id"], task["id"])
        self.assertEqual(self.client.get(
            f"/api/tenants/pr-infra/tasks/{task['id']}"
        ).status_code, 404)


if __name__ == "__main__":
    unittest.main()
