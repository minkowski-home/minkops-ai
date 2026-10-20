"""Device credentials, task dispatch and result replay against real PostgreSQL."""

import base64
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
from fastapi.testclient import TestClient

from minkops_api.main import app

URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class DesktopTests(unittest.TestCase):
    def test_bound_folder_refresh_validates_snapshot_and_replays_once(self):
        self.pair()
        accounts = f"/api/tenants/{self.slug}/accounts"
        content = b"%PDF-1.4 test only"
        source = self.client.post(
            accounts + "/sources",
            headers=self.csrf,
            data={"label": "Office files", "writable": "true", "paths": '["bill.pdf"]'},
            files=[("files", ("bill.pdf", content))],
        ).json()
        bound = self.client.post(
            self.base + f"/devices/{self.device['id']}/sources/{source['id']}", headers=self.csrf
        )
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(
            self.client.get(self.base + "/sources").json()[0]["source_id"], source["id"]
        )
        job, _ = self.launch(operation="files.refresh", input={"source_id": source["id"]})
        joined, joined_body = self.launch(
            operation="files.refresh", input={"source_id": source["id"]}
        )
        self.assertEqual(joined["id"], job["id"])
        claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        route = self.worker_base + f"/jobs/{job['id']}/finish"
        result = {
            "files": [
                {"path": "bill.pdf", "content": base64.b64encode(content + b" refreshed").decode()}
            ]
        }
        receipt = {"claim_token": claim["claim_token"], "result": result}
        invalid = {
            **receipt,
            "result": {
                "files": [{"path": "../bill.pdf", "content": result["files"][0]["content"]}]
            },
        }
        self.assertEqual(
            self.client.post(route, headers=self.worker, json=invalid).status_code, 422
        )
        for _ in range(2):
            done = self.client.post(route, headers=self.worker, json=receipt)
            self.assertEqual(done.status_code, 200, done.text)
            self.assertEqual(done.json()["result"], {"source_id": source["id"], "file_count": 1})
        with psycopg.connect(URL) as c:
            self.assertEqual(
                c.execute(
                    "SELECT count(*) FROM account_files WHERE source_id=%s AND current",
                    (source["id"],),
                ).fetchone()[0],
                1,
            )
        self.assertEqual(
            self.client.post(self.base + "/jobs", headers=self.csrf, json=joined_body).json()["id"],
            job["id"],
        )

    def test_unbound_sources_cannot_be_dispatched(self):
        self.pair()
        response = self.client.post(
            self.base + "/jobs",
            headers=self.csrf,
            json={
                "device_id": self.device["id"],
                "request_key": str(uuid.uuid4()),
                "operation": "files.refresh",
                "input": {"source_id": str(uuid.uuid4())},
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_two_workers_cannot_claim_the_same_attempt(self):
        self.pair()
        job, _ = self.launch()

        def claim(_):
            with TestClient(app) as client:
                return client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, range(2)))
        self.assertEqual(len([c for c in claims if c]), 1)
        self.assertEqual(next(c for c in claims if c)["id"], job["id"])

    def test_revocation_waits_for_authorized_device_work(self):
        from psycopg.rows import dict_row

        from minkops_platform import desktop
        self.pair()
        with psycopg.connect(URL, row_factory=dict_row) as writer:
            tenant_id = writer.execute('SELECT id FROM tenants WHERE slug=%s', (self.slug,)).fetchone()['id']
            device = desktop.owned_device(writer, tenant_id, self.device['owner_id'], self.device['id'])
            with psycopg.connect(URL, row_factory=dict_row) as revoker:
                revoker.execute("SET LOCAL lock_timeout = '250ms'")
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    desktop.revoke(revoker, {'id':device['tenant_id']}, {'id':device['owner_id']}, device['id'])
                revoker.rollback()
        response = self.client.delete(self.base + f"/devices/{self.device['id']}", headers=self.csrf)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.post('/api/desktop/worker/claim', headers=self.worker, json={}).status_code, 401)

    def test_receipt_transport_rejects_malformed_and_oversized_json(self):
        self.pair()
        job, _ = self.launch()
        route = self.worker_base + f"/jobs/{job['id']}/finish"
        for content in [b"broken JSON", b"\xff", b"[]"]:
            self.assertEqual(
                self.client.post(route, headers=self.worker, content=content).status_code, 422
            )
        self.assertEqual(
            self.client.post(route, headers=self.worker, content=b" " * 96_000_001).status_code, 413
        )

    def test_rotation_invalidates_old_credential_and_request_key_cannot_change(self):
        self.pair()
        old = self.worker
        job, body = self.launch()
        rotated = self.client.post(
            self.base + "/devices",
            headers=self.csrf,
            json={"name": "Office PC", "installation_id": self.device["installation_id"]},
        )
        self.assertEqual(rotated.status_code, 201, rotated.text)
        self.assertEqual(rotated.json()["id"], self.device["id"])
        self.assertEqual(
            self.client.post(self.worker_base + "/claim", headers=old, json={}).status_code, 401
        )
        self.worker = {"Authorization": "Bearer " + rotated.json()["credential"], "X-Minkops-Companion-Version": "0.7.0"}
        self.assertEqual(
            self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()[
                "id"
            ],
            job["id"],
        )
        body["input"] = {"source_id": str(uuid.uuid4())}
        body["operation"] = "files.refresh"
        self.assertEqual(
            self.client.post(self.base + "/jobs", headers=self.csrf, json=body).status_code, 409
        )

    def test_another_account_and_workspace_cannot_operate_my_pc(self):
        self.pair()
        job, _ = self.launch()
        visitor = TestClient(app)
        email = f"other-{uuid.uuid4().hex}@example.com"
        response = visitor.post(
            "/api/auth/signup",
            json={
                "name": "Other",
                "email": email,
                "password": "other test password 123!",
                "organization_name": "Other workspace",
            },
        )
        visitor.post(
            "/api/auth/verify",
            json={"token": response.json()["verification_link"].rsplit("/", 1)[1]},
        )
        visitor.post(
            "/api/auth/login", json={"email": email, "password": "other test password 123!"}
        )
        other = visitor.get("/api/auth/me").json()
        other_csrf = {"x-csrf-token": other["csrf_token"]}
        self.assertEqual(visitor.get(self.base + f"/jobs/{job['id']}").status_code, 403)
        # Even membership in my workspace does not delegate my device or grant.
        with psycopg.connect(URL) as c:
            c.execute(
                "INSERT INTO memberships(tenant_id,user_id,role) VALUES ((SELECT id FROM tenants WHERE slug=%s),%s,'member')",
                (self.slug, other["id"]),
            )
        self.assertEqual(visitor.get(self.base + f"/jobs/{job['id']}").status_code, 404)
        self.assertEqual(
            visitor.delete(
                self.base + f"/devices/{self.device['id']}", headers=other_csrf
            ).status_code,
            404,
        )
        self.assertEqual(
            visitor.post(
                self.base + "/jobs",
                headers=other_csrf,
                json={
                    "device_id": self.device["id"],
                    "request_key": str(uuid.uuid4()),
                    "operation": "tally.probe",
                    "input": {},
                },
            ).status_code,
            404,
        )

    def setUp(self):
        os.environ["DATABASE_URL"] = URL
        os.environ["AUTH_DEV_MODE"] = "1"
        self.client = TestClient(app)
        email = f"desktop-{uuid.uuid4().hex}@example.com"
        response = self.client.post(
            "/api/auth/signup",
            json={
                "name": "Desktop Operator",
                "email": email,
                "password": "desktop test password 123!",
                "organization_name": "Desktop Tests",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.client.post(
            "/api/auth/verify",
            json={"token": response.json()["verification_link"].rsplit("/", 1)[1]},
        )
        self.client.post(
            "/api/auth/login", json={"email": email, "password": "desktop test password 123!"}
        )
        self.user = self.client.get("/api/auth/me").json()
        self.slug = self.user["memberships"][0]["slug"]
        self.base = f"/api/tenants/{self.slug}/desktop"
        self.csrf = {"x-csrf-token": self.user["csrf_token"]}

    def pair(self):
        response = self.client.post(
            self.base + "/devices",
            headers=self.csrf,
            json={"name": "Office PC", "installation_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.device = response.json()
        self.worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.7.0"}
        self.worker_base = "/api/desktop/worker"
        return self.device

    def launch(self, **extra):
        body = {
            "device_id": self.device["id"],
            "operation": "tally.probe",
            "request_key": str(uuid.uuid4()),
            "input": {},
        }
        body.update(extra)
        response = self.client.post(self.base + "/jobs", headers=self.csrf, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json(), body

    def test_registration_requires_session_and_csrf_and_hides_secret(self):
        self.assertEqual(TestClient(app).get(self.base + "/devices").status_code, 401)
        self.assertEqual(
            self.client.post(
                self.base + "/devices", json={"name": "PC", "installation_id": str(uuid.uuid4())}
            ).status_code,
            403,
        )
        self.pair()
        devices = self.client.get(self.base + "/devices").json()
        self.assertEqual(len(devices), 1)
        self.assertNotIn("credential", devices[0])
        with psycopg.connect(URL) as c:
            stored = c.execute(
                "SELECT token_hash FROM desktop_devices WHERE id=%s", (self.device["id"],)
            ).fetchone()[0]
        self.assertNotEqual(stored, self.device["credential"])

    def test_web_start_worker_claim_finish_and_idempotent_receipt(self):
        self.pair()
        job, body = self.launch()
        replay = self.client.post(self.base + "/jobs", headers=self.csrf, json=body)
        self.assertEqual(replay.json()["id"], job["id"])
        claimed = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        self.assertEqual(claimed["id"], job["id"])
        self.assertIsNone(
            self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        )
        receipt = {
            "claim_token": claimed["claim_token"],
            "result": {"available": True, "companies": ["Minkops Test"]},
            "error": None,
        }
        route = self.worker_base + f"/jobs/{job['id']}/finish"
        for _ in range(2):
            done = self.client.post(route, headers=self.worker, json=receipt)
            self.assertEqual(done.status_code, 200, done.text)
        changed = {**receipt, "result": {"available": False, "companies": []}}
        self.assertEqual(
            self.client.post(route, headers=self.worker, json=changed).status_code, 409
        )
        task = self.client.get(f"/api/tenants/{self.slug}/tasks/{job['task_id']}").json()
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["progress"], 100)
        self.assertEqual(len(task["events"]), 3)

    def test_arbitrary_commands_and_tally_xml_are_not_dispatchable(self):
        self.pair()
        for operation, payload in [
            ("shell.execute", {"command": "anything"}),
            ("tally.probe", {"url": "http://example.com"}),
            ("tally.probe", {"xml": "<Import/>"}),
        ]:
            response = self.client.post(
                self.base + "/jobs",
                headers=self.csrf,
                json={
                    "device_id": self.device["id"],
                    "request_key": str(uuid.uuid4()),
                    "operation": operation,
                    "input": payload,
                },
            )
            self.assertEqual(response.status_code, 422, response.text)

    def test_revocation_and_lost_membership_stop_worker_access(self):
        self.pair()
        self.client.post(self.worker_base + "/claim", headers=self.worker, json={})
        response = self.client.delete(
            self.base + f"/devices/{self.device['id']}", headers=self.csrf
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).status_code,
            401,
        )
        self.pair()
        with psycopg.connect(URL) as c:
            c.execute("DELETE FROM memberships WHERE user_id=%s", (self.user["id"],))
        self.assertEqual(
            self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).status_code,
            401,
        )

    def test_job_isolation_and_invalid_receipts(self):
        self.pair()
        job, _ = self.launch()
        first = self.worker
        self.pair()
        self.assertIsNone(
            self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        )
        route = self.worker_base + f"/jobs/{job['id']}/finish"
        self.assertEqual(
            self.client.post(
                route,
                headers=self.worker,
                json={
                    "claim_token": str(uuid.uuid4()),
                    "result": {"available": True, "companies": []},
                },
            ).status_code,
            404,
        )
        claim = self.client.post(self.worker_base + "/claim", headers=first, json={}).json()
        self.assertEqual(
            self.client.post(
                route,
                headers=first,
                json={
                    "claim_token": str(uuid.uuid4()),
                    "result": {"available": True, "companies": []},
                },
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                route,
                headers=first,
                json={"claim_token": claim["claim_token"], "result": {"arbitrary": "unvalidated"}},
            ).status_code,
            422,
        )

    def test_interrupted_read_is_reclaimed_with_new_token(self):
        self.pair()
        job, _ = self.launch()
        first = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE desktop_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",
                (job["id"],),
            )
        second = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        self.assertEqual(second["id"], first["id"])
        self.assertNotEqual(second["claim_token"], first["claim_token"])
        late = self.client.post(
            self.worker_base + f"/jobs/{job['id']}/finish",
            headers=self.worker,
            json={
                "claim_token": first["claim_token"],
                "result": {"available": True, "companies": []},
            },
        )
        self.assertEqual(late.status_code, 409, late.text)

    def claim_as(self, headers):
        return self.client.post(self.worker_base + "/claim", headers={"Authorization": self.worker["Authorization"], **headers}, json={})

    def test_each_poll_records_the_companion_version_pc_and_session(self):
        self.pair()
        self.claim_as({"X-Minkops-Companion-Version": "0.7.0", "X-Minkops-Host": "PRAHLAD-GADHWAL",
                       "X-Minkops-Session": "remote"})
        [device] = self.client.get(self.base + "/devices").json()
        self.assertEqual((device["companion_version"], device["hostname"], device["remote_session"]),
                         ("0.7.0", "PRAHLAD-GADHWAL", True))
        self.claim_as({"X-Minkops-Companion-Version": "not a version", "X-Minkops-Host": "x" * 81})
        [device] = self.client.get(self.base + "/devices").json()
        self.assertEqual((device["companion_version"], device["hostname"], device["remote_session"]),
                         (None, None, None), "unreadable reports are never stored as facts")

    def test_tally_work_waits_for_a_current_companion(self):
        self.pair()
        self.launch()  # A PC that has not polled yet: work waits for it.
        self.claim_as({})  # Releases before 0.7.0 poll without reporting a version.
        body = {"device_id": self.device["id"], "operation": "tally.probe", "request_key": str(uuid.uuid4()), "input": {}}
        outdated = self.client.post(self.base + "/jobs", headers=self.csrf, json=body)
        self.assertEqual(outdated.status_code, 409, outdated.text)
        self.assertIn("Update Minkops on Office PC to 0.7.0 or later", outdated.json()["detail"])
        self.claim_as({"X-Minkops-Companion-Version": "0.6.10"})
        self.assertEqual(self.client.post(self.base + "/jobs", headers=self.csrf, json=body).status_code, 409)
        self.claim_as({"X-Minkops-Companion-Version": "0.10.0"})
        self.assertEqual(self.client.post(self.base + "/jobs", headers=self.csrf, json=body).status_code, 202)

    def bundle(self, **extra):
        return {
            "collected_at": "2026-10-14T07:47:18.907Z",
            "companion": {"version": "0.7.0"},
            "windows": {"hostname": "PRAHLAD-GADHWAL", "remote_session": False},
            "tally": {"session": {"state": "not_running"}, "processes": []},
            **extra,
        }

    def stored_diagnostics(self):
        with psycopg.connect(URL) as c:
            return c.execute(
                "SELECT reference,kind,job_id,payload FROM desktop_diagnostics WHERE device_id=%s ORDER BY created_at",
                (self.device["id"],),
            ).fetchall()

    def test_send_diagnostics_stores_a_bounded_bundle_and_returns_a_reference(self):
        self.pair()
        route = self.worker_base + "/diagnostics"
        sent = self.client.post(route, headers=self.worker, json=self.bundle())
        self.assertEqual(sent.status_code, 201, sent.text)
        self.assertRegex(sent.json()["reference"], r"^D-[0-9A-HJKMNP-TV-Z]{6}$")
        [(reference, kind, job_id, payload)] = self.stored_diagnostics()
        self.assertEqual((reference, kind, job_id), (sent.json()["reference"], "requested", None))
        self.assertEqual(payload["windows"]["hostname"], "PRAHLAD-GADHWAL")
        for invalid in (self.bundle(bills=["private"]), self.bundle(tally={"x": "y" * 70_000}), []):
            self.assertEqual(self.client.post(route, headers=self.worker, json=invalid).status_code, 422)
        self.assertEqual(self.client.post(route, json=self.bundle()).status_code, 401)

    def test_diagnostics_older_than_thirty_days_are_removed(self):
        self.pair()
        route = self.worker_base + "/diagnostics"
        self.client.post(route, headers=self.worker, json=self.bundle())
        with psycopg.connect(URL) as c:
            c.execute("UPDATE desktop_diagnostics SET created_at=now()-interval '31 days' WHERE device_id=%s",
                      (self.device["id"],))
        self.client.post(route, headers=self.worker, json=self.bundle())
        self.assertEqual(len(self.stored_diagnostics()), 1)

    def test_a_failed_job_keeps_its_diagnostic_without_blocking_the_receipt(self):
        self.pair()
        for diagnostic, expected in (
            ({"state": "not_running", "cause": "ECONNREFUSED", "elapsed_ms": 4}, "not_running"),
            ({"state": "busy", "error": "x" * 20_000}, None),
        ):
            job, _ = self.launch()
            claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
            receipt = {"claim_token": claim["claim_token"], "error": "Tally isn't open on PC1.",
                       "diagnostic": diagnostic}
            route = self.worker_base + f"/jobs/{job['id']}/finish"
            for _ in range(2):  # a replayed receipt stores nothing twice
                self.assertEqual(self.client.post(route, headers=self.worker, json=receipt).status_code, 200)
            stored = [row for row in self.stored_diagnostics() if str(row[2]) == job["id"]]
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0][1], "job")
            if expected:
                self.assertEqual(stored[0][3]["state"], expected)
            else:
                self.assertEqual(stored[0][3], {"truncated": True})

    def test_error_finishes_as_failure_without_fake_completion(self):
        self.pair()
        job, _ = self.launch()
        claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        response = self.client.post(
            self.worker_base + f"/jobs/{job['id']}/finish",
            headers=self.worker,
            json={
                "claim_token": claim["claim_token"],
                "error": "Tally is not responding. Open Tally and try again.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        task = self.client.get(f"/api/tenants/{self.slug}/tasks/{job['task_id']}").json()
        self.assertEqual(task["status"], "failed")
        self.assertLess(task["progress"], 100)
