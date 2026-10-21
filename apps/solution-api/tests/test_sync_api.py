"""The sync over HTTP: a PC's companion collects, the server decides and publishes."""

import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from pwdlib import PasswordHash

from minkops_api.main import app

URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "long test password 123!"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform/tests"))


@unittest.skipUnless(URL, "TEST_DATABASE_URL required")
class SyncApiTests(unittest.TestCase):
    def setUp(self):
        import factory
        os.environ["DATABASE_URL"] = URL
        with psycopg.connect(URL, row_factory=dict_row) as db:
            self.tenant = factory.tenant(db)
            self.admin = factory.user(db, self.tenant, role="admin")
            db.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                       (PasswordHash.recommended().hash(PASSWORD), self.admin["id"]))
            self.client_row = factory.client(db, self.tenant)
        self.web = TestClient(app)
        self.assertEqual(self.web.post("/api/auth/login", json={"email": self.admin["email"], "password": PASSWORD}).status_code, 200)
        self.csrf = {"x-csrf-token": self.web.get("/api/auth/me").json()["csrf_token"]}
        self.base = f"/api/tenants/{self.tenant['slug']}"
        device = self.web.post(self.base + "/desktop/devices", headers=self.csrf,
                               json={"name": "TEST-PC", "installation_id": str(uuid4())}).json()
        self.device_id = device["id"]
        self.pc = TestClient(app)
        self.pc.headers.update({"Authorization": f"Bearer {device['credential']}", "X-Minkops-Companion-Version": "0.10.0"})

    def claim(self):
        self.assertEqual(self.web.post(f"{self.base}/desktop/devices/{self.device_id}/sync", headers=self.csrf).status_code, 202)
        job = self.pc.post("/api/desktop/worker/claim").json()
        self.assertEqual(job["operation"], "tally.sync")
        return job

    def page(self, job, seq, kind, **body):
        response = self.pc.post(f"/api/desktop/worker/jobs/{job['id']}/sync",
                                json={"claim_token": job["claim_token"], "seq": seq, "kind": kind, **body})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def finish(self, job, companies):
        response = self.pc.post(f"/api/desktop/worker/jobs/{job['id']}/finish",
                                json={"claim_token": job["claim_token"], "result": {"protocol": 1, "companies": companies}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_new_company_is_authorised_once_then_mirrored_by_the_next_sync(self):
        identity = {"name": "Rehearsal Co", "guid": str(uuid4()), "company_number": "100000", "books_from": "2026-04-01",
                    "markers": {"alt_mst_id": 1, "alt_vch_id": 1}}
        job = self.claim()
        plan = self.pc.get(f"/api/desktop/worker/jobs/{job['id']}/plan", params={"claim_token": job["claim_token"]}).json()
        self.assertEqual((plan["protocol"], plan["port"], plan["companies"]), (1, 9000, []))
        step = self.page(job, 0, "companies", companies=[identity])["instructions"][0]
        self.assertEqual((step["mode"], step["reason"]), ("skip", "pending"))
        self.assertEqual(self.page(job, 0, "companies", companies=[identity])["instructions"][0], step)  # A resend is safe.
        self.assertEqual(self.finish(job, [])["state"], "completed")
        (company,) = self.web.get(f"{self.base}/desktop/devices/{self.device_id}/companies").json()
        self.assertEqual(company["status"], "pending")
        authorised = self.web.post(f"{self.base}/companies/{company['id']}/authorise", headers=self.csrf,
                                   json={"client": self.client_row["slug"]})
        self.assertEqual(authorised.status_code, 200, authorised.text)
        # Authorising queued the company's first full sync.
        job = self.pc.post("/api/desktop/worker/claim").json()
        self.assertEqual(job["operation"], "tally.sync")
        step = self.page(job, 0, "companies", companies=[identity])["instructions"][0]
        self.assertEqual((step["mode"], step["reason"]), ("full", "first_sync"))
        ledger = {"type": "LEDGER", "data": {"@_NAME": "Acme", "GUID": f"{identity['guid']}-1", "ALTERID": "1"}}
        self.page(job, 1, "masters", company=step["company"], records=[ledger])
        voucher = {"GUID": f"{identity['guid']}-v1", "ALTERID": "1", "DATE": "20260901", "VOUCHERTYPENAME": "Payment"}
        self.page(job, 2, "vouchers", company=step["company"], records=[voucher])
        # Tally's own count agrees with what was collected, so no census is needed.
        self.assertEqual(self.page(job, 3, "counts", company=step["company"], counts={"2026-09-01": 1})["census"], [])
        self.finish(job, [{"company": step["company"], "complete": True}])
        (company,) = self.web.get(f"{self.base}/desktop/devices/{self.device_id}/companies").json()
        self.assertEqual((company["status"], company["version"], company["kind"]), ("authorised", 1, "full"))

    def test_pages_need_their_own_claim_and_a_running_sync(self):
        job = self.claim()
        response = self.pc.post(f"/api/desktop/worker/jobs/{job['id']}/sync",
                                json={"claim_token": str(uuid4()), "seq": 0, "kind": "companies", "companies": []})
        self.assertEqual(response.status_code, 409)
        self.finish(job, [])
        late = self.pc.post(f"/api/desktop/worker/jobs/{job['id']}/sync",
                            json={"claim_token": job["claim_token"], "seq": 0, "kind": "companies", "companies": []})
        self.assertEqual(late.status_code, 409)

    def test_a_sync_that_stalled_is_replaced_and_its_partial_build_reverted(self):
        identity = {"name": "Stalled Co", "guid": str(uuid4()), "company_number": "100000", "books_from": "2026-04-01",
                    "markers": {"alt_mst_id": 1, "alt_vch_id": 0}}
        first = self.claim()
        self.page(first, 0, "companies", companies=[identity])
        with psycopg.connect(URL) as db:
            db.execute("UPDATE desktop_jobs SET lease_until=now()-interval '1 minute' WHERE id=%s", (first["id"],))
        second = self.claim()
        self.assertNotEqual(second["id"], first["id"])
        with psycopg.connect(URL, row_factory=dict_row) as db:
            state = db.execute("SELECT state FROM desktop_jobs WHERE id=%s", (first["id"],)).fetchone()["state"]
        self.assertEqual(state, "failed")

    def test_only_the_owner_or_an_admin_sets_the_tally_port(self):
        response = self.web.patch(f"{self.base}/desktop/devices/{self.device_id}", headers=self.csrf, json={"tally_port": 9999})
        self.assertEqual(response.json(), {"device_id": self.device_id, "tally_port": 9999})
        job = self.claim()
        plan = self.pc.get(f"/api/desktop/worker/jobs/{job['id']}/plan", params={"claim_token": job["claim_token"]}).json()
        self.assertEqual(plan["port"], 9999)
        self.assertEqual(self.web.patch(f"{self.base}/desktop/devices/{self.device_id}", headers=self.csrf,
                                        json={"tally_port": 0}).status_code, 422)
