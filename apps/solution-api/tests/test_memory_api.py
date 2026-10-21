"""A client's memory over HTTP: every member who can reach the client reads it, and only admins change it."""

import os
import sys
import unittest
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from pwdlib import PasswordHash

from minkops_api.main import app
from minkops_platform.accounts import memory

URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "long test password 123!"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform/tests"))


@unittest.skipUnless(URL, "TEST_DATABASE_URL required")
class MemoryApiTests(unittest.TestCase):
    def setUp(self):
        import factory
        os.environ["DATABASE_URL"] = URL
        hashed = PasswordHash.recommended().hash(PASSWORD)
        with psycopg.connect(URL, row_factory=dict_row) as db:
            self.tenant = factory.tenant(db)
            self.admin, self.clerk = factory.user(db, self.tenant, role="admin"), factory.user(db, self.tenant)
            db.execute("UPDATE users SET password_hash=%s WHERE id = ANY(%s)",
                       (hashed, [self.admin["id"], self.clerk["id"]]))
            client = factory.client(db, self.tenant)
            company = factory.company(db, self.tenant, factory.device(db, self.tenant, self.admin), client)
            self.entry = memory.record(db, tenant_id=self.tenant["id"], client_id=client["id"],
                                       company_id=company["id"], kind="practice", subject="receipt_register",
                                       value={"recorded_in": "narration"}, evidence={"kind": "probe"},
                                       status="confirmed")
            self.base = f"/api/tenants/{self.tenant['slug']}/clients/{client['slug']}/memory"

    def login(self, user):
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return client, {"x-csrf-token": client.get("/api/auth/me").json()["csrf_token"]}

    def test_members_read_memory_and_only_admins_change_it(self):
        clerk, clerk_csrf = self.login(self.clerk)
        page = clerk.get(self.base).json()
        self.assertEqual((page["can_edit"], [e["subject"] for e in page["entries"]], page["rules"]),
                         (False, ["receipt_register"], []))
        entry = f"{self.base}/entries/{self.entry['id']}"
        self.assertEqual(clerk.patch(entry, headers=clerk_csrf, json={"status": "disabled"}).status_code, 403)
        self.assertEqual(clerk.post(f"{self.base}/rules", headers=clerk_csrf, json={"text": "Never."}).status_code, 403)
        admin, csrf = self.login(self.admin)
        self.assertEqual(admin.patch(entry, json={"status": "disabled"}).status_code, 403)  # No CSRF token.
        self.assertEqual(admin.patch(entry, headers=csrf, json={"status": "disabled"}).json()["status"], "disabled")
        rule = admin.post(f"{self.base}/rules", headers=csrf,
                          json={"text": "Book NEFT returns as two entries.", "workflow_key": "statement-entry"}).json()
        edited = admin.put(f"{self.base}/rules/{rule['id']}", headers=csrf,
                           json={"text": "Book both legs of a NEFT return.", "workflow_key": "statement-entry"}).json()
        self.assertEqual((rule["version"], edited["version"], edited["text"]),
                         (1, 2, "Book both legs of a NEFT return."))
        self.assertEqual(admin.patch(f"{self.base}/rules/{rule['id']}", headers=csrf,
                                     json={"status": "disabled"}).json()["status"], "disabled")
        page = admin.get(self.base).json()
        self.assertEqual(([e["status"] for e in page["entries"]], [(r["status"], r["version"]) for r in page["rules"]]),
                         (["disabled"], [("disabled", 3)]))
        self.assertEqual(admin.delete(f"{self.base}/rules/{rule['id']}", headers=csrf).json()["status"], "deleted")
        self.assertEqual(admin.get(self.base).json()["rules"], [])
