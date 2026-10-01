"""Real database/auth tests; replace only the paid hosted agent boundary."""

import json
import os
import unittest
import uuid

import psycopg
from fastapi.testclient import TestClient
from minkops_api.main import app
from psycopg.rows import dict_row
from test_accounts_excel import catalog, workbook

URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class AccountsTests(unittest.TestCase):
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

    def verify_flow(self, cancel=False):
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
        # Cancellation releases the pending reservation and keeps a late
        # receipt honest if the browser saved before losing its connection.
        if cancel:
            cancelled = self.client.post(
                self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf
            )
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["state"], "failed")
            self.assertEqual(self.client.get(path + "/content").status_code, 409)
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
