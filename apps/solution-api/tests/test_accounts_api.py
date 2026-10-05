"""Real database/auth tests; replace only the paid hosted agent boundary."""

import json
import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient
from minkops_api.main import app
from psycopg.rows import dict_row
from test_accounts_excel import catalog, workbook

URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class AccountsTests(unittest.TestCase):
    def test_launch_pins_complete_definition_and_replay_keeps_the_original_bundle(self):
        from minkops_platform.runtime.bundles import validate_snapshot

        run, body = self.launch()
        snapshot = run["config"]["execution_snapshot"]
        validate_snapshot(snapshot)
        self.assertEqual(snapshot["definition_version"], run["definition_version"])
        self.assertEqual(snapshot["files"]["SKILL.md"], run["config"]["instructions_snapshot"])
        self.assertEqual(
            json.loads(snapshot["files"]["agent-output.schema.json"]),
            run["config"]["agent_output_schema"],
        )
        with patch(
            "minkops_platform.accounts.service.load_definition",
            side_effect=AssertionError("new checkout"),
        ):
            replay = self.client.post(self.base + "/runs", headers=self.csrf, json=body)
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertEqual(replay.json()["config"]["execution_snapshot"], snapshot)

    def test_worker_respects_an_existing_database_run_lock(self):
        from minkops_platform.accounts.worker import STORE, work_once

        run, _ = self.launch()
        executor = MagicMock()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (run["id"],))
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            with patch.object(STORE, "candidates", return_value=[row]):
                self.assertFalse(work_once(URL, executor=executor))
            c.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (run["id"],))
        executor.assert_not_called()

    def test_invalid_agent_proposal_remains_durable_for_diagnostics(self):
        from jsonschema import ValidationError
        from minkops_platform.accounts.worker import process

        run, _ = self.launch()
        received = {"unexpected": "raw proposal"}
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            with self.assertRaises(ValidationError):
                process(c, row, executor=lambda *a, **k: received)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            saved = c.execute(
                "SELECT result FROM account_runs WHERE id=%s", (run["id"],)
            ).fetchone()
            self.assertEqual(saved["result"], received)

    def test_legacy_unpinned_queued_run_fails_without_calling_the_agent(self):
        from minkops_platform.accounts.worker import STORE, work_once

        run, _ = self.launch()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute(
                "UPDATE account_runs SET config=config-'execution_snapshot' WHERE id=%s",
                (run["id"],),
            )
            c.commit()
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
        executor = MagicMock()
        with patch.object(STORE, "candidates", return_value=[row]):
            self.assertTrue(work_once(URL, executor=executor))
        executor.assert_not_called()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute(
                "SELECT state,error FROM account_runs WHERE id=%s", (run["id"],)
            ).fetchone()
        self.assertEqual(row["state"], "failed")
        self.assertIn("execution bundle", row["error"])

    def test_two_destinations_can_share_a_relative_filename(self):
        second = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"label": "Second folder", "writable": "true", "paths": '["records.xlsx"]'},
            files=[("files", ("records.xlsx", workbook()))],
        ).json()
        second_id = second["files"][0]["id"]
        discovery, _ = self.launch(file_ids=[self.file_id, second_id])
        proposals = []
        for file_id in [self.file_id, second_id]:
            mapping = catalog()["sheets"][0]
            mapping["file_id"] = file_id
            proposals.append(mapping)
            proposals.append(
                {
                    "file_id": file_id,
                    "sheet": "Other",
                    "header_row": 1,
                    "role": "ignore",
                    "key_columns": [],
                    "columns": [],
                }
            )
        expected = {"sheets": proposals}
        from minkops_api.accounts_worker import process

        with psycopg.connect(URL, row_factory=dict_row) as c:
            process(
                c,
                c.execute("SELECT * FROM account_runs WHERE id=%s", (discovery["id"],)).fetchone(),
                executor=lambda *a, **k: expected,
            )
        approved = self.client.post(
            self.base + f"/runs/{discovery['id']}/approve",
            headers=self.csrf,
            json={"result": expected},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        bill = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"paths": '["bill.pdf"]'},
            files=[("files", ("bill.pdf", b"%PDF-1.4 test"))],
        ).json()["files"][0]["id"]
        run, _ = self.launch(
            "bill-entry", file_ids=[bill], catalog_id=approved.json()["catalog_id"]
        )
        data = {"Invoice": "A-2", "Vendor": "Acme", "Amount": 24}
        result = {
            "findings": [],
            "records": [
                {
                    "source_file_id": bill,
                    "destination_file_id": file_id,
                    "sheet": "Bills",
                    "operation": "append",
                    "data": dict(data),
                    "evidence": [
                        {"field": key, "page": 1, "quote": str(value)}
                        for key, value in data.items()
                    ],
                    "findings": [],
                }
                for file_id in [self.file_id, second_id]
            ],
        }
        with psycopg.connect(URL, row_factory=dict_row) as c:
            process(
                c,
                c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone(),
                executor=lambda *a, **k: result,
            )
        approved = self.client.post(
            self.base + f"/runs/{run['id']}/approve",
            headers=self.csrf,
            json={"result": result, "acknowledge_findings": True},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(len(approved.json()["writes"]), 2)
        self.assertEqual(len({w["source_id"] for w in approved.json()["writes"]}), 2)
        self.client.post(self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf)

    def setUp(self):
        os.environ["DATABASE_URL"] = URL
        self.client = TestClient(app)
        response = self.client.post(
            "/api/auth/login",
            json={"email": "demo@example.com", "password": "long test password 123!"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.csrf = {"x-csrf-token": self.client.get("/api/auth/me").json()["csrf_token"]}
        self.base = "/api/tenants/mock-tenant/accounts"
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE workflows SET status='active' WHERE key IN ('bill-entry','source-discovery') AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant')"
            )
        response = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={
                "label": "Test folder",
                "writable": "true",
                "paths": json.dumps(["records.xlsx"]),
            },
            files=[("files", ("records.xlsx", workbook()))],
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.source = response.json()
        self.file_id = self.source["files"][0]["id"]

    def launch(self, key="source-discovery", **changes):
        body = {"key": key, "request_key": str(uuid.uuid4()), "file_ids": [self.file_id], **changes}
        response = self.client.post(self.base + "/runs", headers=self.csrf, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json(), body

    def execute_discovery(self):
        run, _ = self.launch()
        expected = catalog()
        expected["sheets"][0]["file_id"] = self.file_id
        expected["sheets"].append(
            {
                "file_id": self.file_id,
                "sheet": "Other",
                "header_row": 1,
                "role": "ignore",
                "key_columns": [],
                "columns": [
                    {"name": "Keep me", "type": "string", "concept": "", "required": False}
                ],
            }
        )

        def fake(key, files, context, event, **kwargs):
            event("agent.session.turn.created", "session-test", "turn-test")
            return expected

        # Explicitly process this test's run, independent of other queued work.
        from minkops_api.accounts_worker import process

        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            process(c, row, executor=fake)
        response = self.client.post(
            self.base + f"/runs/{run['id']}/approve", headers=self.csrf, json={"result": expected}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["catalog_id"]

    def test_launch_idempotency_and_tenant_isolation(self):
        run, body = self.launch()
        again = self.client.post(self.base + "/runs", headers=self.csrf, json=body)
        self.assertEqual(again.json()["id"], run["id"])
        changed = {**body, "config": {"max_files": 2}}
        self.assertEqual(
            self.client.post(self.base + "/runs", headers=self.csrf, json=changed).status_code, 409
        )
        self.assertEqual(
            self.client.get("/api/tenants/pr-infra/accounts/runs/" + run["id"]).status_code, 404
        )
        self.assertEqual(self.client.post(self.base + "/runs", json=body).status_code, 403)

    def test_invented_catalog_and_path_traversal_rejected(self):
        run, _ = self.launch()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE account_runs SET state='review' WHERE id=%s", (run["id"],))
        bad = catalog()
        bad["sheets"][0]["file_id"] = self.file_id
        bad["sheets"][0]["sheet"] = "Invented"
        self.assertEqual(
            self.client.post(
                self.base + f"/runs/{run['id']}/approve", headers=self.csrf, json={"result": bad}
            ).status_code,
            422,
        )
        response = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"paths": '["../outside.xlsx"]'},
            files=[("files", ("x.xlsx", workbook()))],
        )
        self.assertEqual(response.status_code, 422)

    def test_full_review_write_receipt_and_repeat_bill(self):
        self.verify_flow()

    def test_cancelled_save_accepts_late_receipt_without_claiming_completion(self):
        self.verify_flow(cancel=True)

    def test_desktop_save_uses_domain_approval_and_verifies_actual_bytes(self):
        self.verify_flow(desktop=True)

    def test_desktop_cancel_blocks_new_save_but_accepts_late_verified_receipt(self):
        self.verify_flow(desktop=True, cancel=True)

    def verify_flow(self, cancel=False, desktop=False):
        cat_id = self.execute_discovery()
        bill = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"paths": '["bill.pdf"]'},
            files=[("files", ("bill.pdf", b"%PDF-1.4 fake boundary test"))],
        ).json()["files"][0]["id"]
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat_id)
        result = {
            "records": [
                {
                    "source_file_id": bill,
                    "destination_file_id": self.file_id,
                    "sheet": "Bills",
                    "operation": "append",
                    "data": {"Invoice": "A-2", "Vendor": "Acme", "Amount": 24},
                    "evidence": [
                        {"field": k, "page": 1, "quote": str(v)}
                        for k, v in {"Invoice": "A-2", "Vendor": "Acme", "Amount": 24}.items()
                    ],
                    "findings": [],
                }
            ],
            "findings": [],
        }

        def fake(*args, **kwargs):
            return result

        from minkops_api.accounts_worker import process

        with psycopg.connect(URL, row_factory=dict_row) as c:
            process(
                c,
                c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone(),
                executor=fake,
            )
        response = self.client.post(
            self.base + f"/runs/{run['id']}/approve",
            headers=self.csrf,
            json={"result": result, "acknowledge_findings": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "writing")
        write = response.json()["writes"][0]
        path = self.base + f"/runs/{run['id']}/writes/{write['id']}"
        content = self.client.get(path + "/content").content
        if desktop:
            import base64

            native_base = "/api/tenants/mock-tenant/desktop"
            device = self.client.post(
                native_base + "/devices",
                headers=self.csrf,
                json={"name": "Accounts PC", "installation_id": str(uuid.uuid4())},
            ).json()
            worker_headers = {"Authorization": "Bearer " + device["credential"]}
            bound = self.client.post(
                native_base + f"/devices/{device['id']}/sources/{self.source['id']}",
                headers=self.csrf,
            )
            self.assertEqual(bound.status_code, 200, bound.text)
            payload = {
                "device_id": device["id"],
                "request_key": str(uuid.uuid4()),
                "operation": "accounts.save",
                "input": {"run_id": run["id"], "write_id": write["id"]},
            }
            job_response = self.client.post(native_base + "/jobs", headers=self.csrf, json=payload)
            self.assertEqual(job_response.status_code, 202, job_response.text)
            job = job_response.json()
            claim = self.client.post(
                "/api/desktop/worker/claim", headers=worker_headers, json={}
            ).json()
            progress = self.client.get("/api/tenants/mock-tenant/tasks/" + job["task_id"]).json()
            self.assertEqual(progress["events"][-1]["event_type"], "local_saving")
            self.assertEqual(progress["status"], "handoff")
            route = f"/api/desktop/worker/jobs/{job['id']}"
            plan_url = route + "/plan?claim_token=" + claim["claim_token"]
            plan = self.client.get(plan_url, headers=worker_headers)
            self.assertEqual(plan.status_code, 200, plan.text)
            self.assertEqual(base64.b64decode(plan.json()["content"]), content)
            # Expiring a financial save cannot silently dispatch it twice.
            with psycopg.connect(URL) as c:
                c.execute(
                    "UPDATE desktop_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",
                    (job["id"],),
                )
            self.assertIsNone(
                self.client.post(
                    "/api/desktop/worker/claim", headers=worker_headers, json={}
                ).json()
            )
        # Cancellation releases the pending reservation and keeps a late
        # receipt honest if the browser saved before losing its connection.
        if cancel:
            cancelled = self.client.post(
                self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf
            )
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["state"], "failed")
            self.assertEqual(self.client.get(path + "/content").status_code, 409)
            if desktop:
                self.assertEqual(self.client.get(plan_url, headers=worker_headers).status_code, 409)
        if desktop:
            receipt = {
                "claim_token": claim["claim_token"],
                "result": {"content": base64.b64encode(content).decode()},
            }
            invalid = {**receipt, "result": {"content": base64.b64encode(b"wrong").decode()}}
            self.assertEqual(
                self.client.post(
                    route + "/finish", headers=worker_headers, json=invalid
                ).status_code,
                409,
            )
            for _ in range(2):
                done = self.client.post(route + "/finish", headers=worker_headers, json=receipt)
                self.assertEqual(done.status_code, 200, done.text)
        invalid = self.client.post(
            path + "/verify", headers=self.csrf, files={"file": ("records.xlsx", b"wrong")}
        )
        self.assertEqual(invalid.status_code, 409)
        verified = self.client.post(
            path + "/verify", headers=self.csrf, files={"file": ("records.xlsx", content)}
        )
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(verified.json()["state"], "failed" if cancel else "completed")
        self.assertIsNotNone(verified.json()["writes"][0]["verified_at"])
        again = self.client.post(
            path + "/verify", headers=self.csrf, files={"file": ("records.xlsx", content)}
        )
        self.assertEqual(again.status_code, 200)
        # Own verified appends advance the catalog snapshot without rediscovery.
        next_run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat_id)
        self.assertNotEqual(
            next_run["config"]["catalog_snapshot"]["sheets"][0]["file_id"], self.file_id
        )
