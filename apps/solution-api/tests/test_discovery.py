"""Discovery uses real database dispatch and confirmation; no fake local executor."""

import base64
import hashlib
import os
import unittest
import uuid
from io import BytesIO

import psycopg
import test_desktop
from psycopg.rows import dict_row
from test_accounts_excel import catalog, workbook

URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class DiscoveryTests(unittest.TestCase):
    setUp = test_desktop.DesktopTests.setUp
    pair = test_desktop.DesktopTests.pair

    def test_damaged_workbook_is_a_validation_error_not_a_backend_crash(self):
        r = self.client.post(
            f"/api/tenants/{self.slug}/accounts/sources",
            headers=self.csrf,
            data={"label": "Damaged", "writable": "true", "paths": '["bad.xlsx"]'},
            files=[("files", ("bad.xlsx", b"not an xlsx archive"))],
        )
        self.assertEqual(r.status_code, 422, r.text)

    def test_excel_and_tally_collection_review_reuse_and_layout_change(self):
        from minkops_platform.accounts.worker import process
        from minkops_platform.resources import REPOSITORY_ROOT
        from minkops_platform.workflows import load_definition
        from openpyxl import load_workbook
        from psycopg.types.json import Jsonb

        self.pair()
        self.discovery = f"/api/tenants/{self.slug}/discovery"
        accounts = f"/api/tenants/{self.slug}/accounts"
        definition = load_definition(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/source-discovery"
        )
        with psycopg.connect(URL) as c:
            c.execute(
                "INSERT INTO workflows(tenant_id,key,name,description,status,config_schema,config_values) SELECT id,'source-discovery','Discovery','Test','active',%s,%s FROM tenants WHERE slug=%s",
                (
                    Jsonb(definition.tenant_schema),
                    Jsonb(definition.metadata["tenant_defaults"]),
                    self.slug,
                ),
            )
        data = workbook()
        source = self.client.post(
            accounts + "/sources",
            headers=self.csrf,
            data={
                "label": "Mock books",
                "writable": "true",
                "paths": '["register.xlsx","bill.pdf"]',
            },
            files=[
                ("files", ("register.xlsx", data)),
                ("files", ("bill.pdf", b"%PDF-1.4 fixture")),
            ],
        ).json()
        self.assertEqual(
            self.client.post(
                self.base + f"/devices/{self.device['id']}/sources/{source['id']}",
                headers=self.csrf,
            ).status_code,
            200,
        )
        config = {"depth": "business_mappings", "excel_source_ids": [source["id"]], "tally": None}

        def scan(content):
            response = self.client.post(
                self.discovery + "/runs",
                headers=self.csrf,
                json={
                    "device_id": self.device["id"],
                    "request_key": str(uuid.uuid4()),
                    "config": config,
                },
            )
            self.assertEqual(response.status_code, 202, response.text)
            run = response.json()
            claim = self.client.post(
                self.worker_base + "/claim", headers=self.worker, json={}
            ).json()
            plan = self.client.get(
                self.worker_base + f"/jobs/{claim['id']}/plan?claim_token={claim['claim_token']}",
                headers=self.worker,
            )
            self.assertEqual(plan.status_code, 200, plan.text)
            for status in ("reading", "ready"):
                observed = self.client.post(
                    self.worker_base + f"/jobs/{claim['id']}/progress",
                    headers=self.worker,
                    json={
                        "claim_token": claim["claim_token"],
                        "source_key": source["id"],
                        "status": status,
                    },
                )
                self.assertEqual(observed.status_code, 200, observed.text)
            w = load_workbook(BytesIO(content))
            receipt = {
                "claim_token": claim["claim_token"],
                "result": {
                    "sources": [
                        {
                            "key": source["id"],
                            "tool": "excel",
                            "status": "ready",
                            "files": [
                                {
                                    "path": "register.xlsx",
                                    "content": base64.b64encode(content).decode(),
                                }
                            ],
                            "workbooks": [
                                {
                                    "path": "register.xlsx",
                                    "sha256": hashlib.sha256(content).hexdigest(),
                                    "status": "ready",
                                    "structure": {
                                        "sheets": [{"sheet": s.title, "tables": []} for s in w]
                                    },
                                }
                            ],
                        }
                    ]
                },
            }
            for _ in range(2):
                r = self.client.post(
                    self.worker_base + f"/jobs/{claim['id']}/finish",
                    headers=self.worker,
                    json=receipt,
                )
                self.assertEqual(r.status_code, 200, r.text)
            return self.client.get(self.discovery + f"/runs/{run['id']}").json()

        first = scan(data)
        self.assertEqual(first["state"], "queued")
        mapping = first["mapping_run"]
        proposal = catalog()
        proposal["sheets"][0]["file_id"] = mapping["file_ids"][0]
        proposal["sheets"].append(
            {
                "file_id": mapping["file_ids"][0],
                "sheet": "Other",
                "table": None,
                "header_row": 1,
                "role": "ignore",
                "key_columns": [],
                "columns": [
                    {"name": "Keep me", "type": "string", "concept": "", "required": False}
                ],
            }
        )

        def executor(key, files, context, event, **kwargs):
            self.assertEqual(context["local_discovery"]["sources"][0]["tool"], "excel")
            return proposal

        with psycopg.connect(URL, row_factory=dict_row) as c:
            process(
                c,
                c.execute("SELECT * FROM account_runs WHERE id=%s", (mapping["id"],)).fetchone(),
                executor=executor,
            )
        confirmed = self.client.post(
            self.discovery + f"/runs/{first['id']}/confirm",
            headers=self.csrf,
            json={"excel_mappings": proposal},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertTrue(confirmed.json()["ready"])
        w = load_workbook(BytesIO(data))
        w["Bills"].append(["A-2", "Acme", 24, "=C4*2"])
        buf = BytesIO()
        w.save(buf)
        second = scan(buf.getvalue())
        self.assertEqual(second["state"], "completed")
        self.assertTrue(second["ready"])
        self.assertNotEqual(
            second["catalog"]["excel_mappings"]["sheets"][0]["file_id"], mapping["file_ids"][0]
        )
        self.assertIn(
            "bill.pdf",
            [f["path"] for f in self.client.get(accounts + "/sources").json()[0]["files"]],
        )
        w["Bills"]["C2"] = "Gross amount"
        buf = BytesIO()
        w.save(buf)
        changed = scan(buf.getvalue())
        self.assertEqual(changed["state"], "queued")
        self.assertFalse(changed["ready"])

    def start(self, **extra):
        self.pair()
        with psycopg.connect(URL) as c:
            c.execute(
                "INSERT INTO workflows(tenant_id,key,name,description,status) SELECT id,'source-discovery','Source discovery','Test','active' FROM tenants WHERE slug=%s ON CONFLICT DO NOTHING",
                (self.slug,),
            )
        self.discovery = f"/api/tenants/{self.slug}/discovery"
        body = {
            "device_id": self.device["id"],
            "request_key": str(uuid.uuid4()),
            "config": {
                "depth": "business_mappings",
                "excel_source_ids": [],
                "tally": {"company": "Test", "port": 9000, "categories": ["ledgers", "units"]},
            },
        }
        body.update(extra)
        r = self.client.post(self.discovery + "/runs", headers=self.csrf, json=body)
        self.assertEqual(r.status_code, 202, r.text)
        return r.json(), body

    def collect(self, run, partial=False):
        claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        result = {
            "sources": [
                {
                    "key": "tally",
                    "tool": "tally",
                    "status": "ready",
                    "snapshot": {
                        "company": "Test",
                        "port": 9000,
                        "collections": [
                            {
                                "category": "ledgers",
                                "status": "ready",
                                "count": 1,
                                "fields": ["NAME"],
                                "records": [{"NAME": "Supplier"}],
                            },
                            {"category": "units", "status": "unavailable", "error": "Unavailable"}
                            if partial
                            else {
                                "category": "units",
                                "status": "ready",
                                "count": 0,
                                "fields": [],
                                "records": [],
                            },
                        ],
                    },
                }
            ]
        }
        r = self.client.post(
            self.worker_base + f"/jobs/{claim['id']}/finish",
            headers=self.worker,
            json={"claim_token": claim["claim_token"], "result": result},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return self.client.get(self.discovery + f"/runs/{run['id']}").json()

    def test_partial_results_are_observable_downloadable_and_cannot_be_confirmed(self):
        run, _ = self.start()
        done = self.collect(run, partial=True)
        self.assertEqual(done["state"], "review")
        self.assertFalse(done["ready"])
        self.assertTrue(done["catalog"]["partial"])
        self.assertEqual(
            self.client.post(
                self.discovery + f"/runs/{run['id']}/confirm", headers=self.csrf, json={}
            ).status_code,
            409,
        )
        download = self.client.get(self.discovery + f"/runs/{run['id']}/catalog.json")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download.headers["content-disposition"])
        self.assertEqual(download.json()["sources"][0]["snapshot"]["collections"][0]["count"], 1)

    def test_confirmation_and_unchanged_refresh_reuse_review_with_idempotence(self):
        run, body = self.start()
        self.assertEqual(
            self.client.post(self.discovery + "/runs", headers=self.csrf, json=body).json()["id"],
            run["id"],
        )
        self.collect(run)
        confirmed = self.client.post(
            self.discovery + f"/runs/{run['id']}/confirm", headers=self.csrf, json={}
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertTrue(confirmed.json()["ready"])
        body["request_key"] = str(uuid.uuid4())
        refresh = self.client.post(self.discovery + "/runs", headers=self.csrf, json=body).json()
        again = self.collect(refresh)
        self.assertEqual(again["state"], "completed")
        self.assertTrue(again["ready"])
        self.assertEqual(again["catalog"]["review"]["reused_from"], run["id"])

    def test_scope_receipts_and_configuration_cannot_escape_the_requested_sources(self):
        run, _ = self.start()
        claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        route = self.worker_base + f"/jobs/{claim['id']}/finish"
        bad = {
            "claim_token": claim["claim_token"],
            "result": {
                "sources": [{"key": "foreign", "tool": "excel", "status": "ready", "snapshot": {}}]
            },
        }
        self.assertEqual(self.client.post(route, headers=self.worker, json=bad).status_code, 422)
        self.assertEqual(
            self.client.get("/api/tenants/mock-tenant/discovery/runs/" + run["id"]).status_code, 403
        )
        config = {
            "depth": "structure",
            "excel_source_ids": [],
            "tally": {"company": "Test", "port": 9000, "categories": ["arbitrary"]},
        }
        self.assertEqual(
            self.client.post(
                self.discovery + "/runs",
                headers=self.csrf,
                json={
                    "device_id": self.device["id"],
                    "request_key": str(uuid.uuid4()),
                    "config": config,
                },
            ).status_code,
            422,
        )
        config["tally"] = None
        config["excel_source_ids"] = ["not-a-uuid"]
        self.assertEqual(
            self.client.post(
                self.discovery + "/runs",
                headers=self.csrf,
                json={
                    "device_id": self.device["id"],
                    "request_key": str(uuid.uuid4()),
                    "config": config,
                },
            ).status_code,
            422,
        )

    def test_revocation_stops_discovery_and_progress_cannot_change_a_replaced_attempt(self):
        run, _ = self.start()
        claim = self.client.post(self.worker_base + "/claim", headers=self.worker, json={}).json()
        route = self.worker_base + f"/jobs/{claim['id']}/progress"
        r = self.client.post(
            route,
            headers=self.worker,
            json={"claim_token": str(uuid.uuid4()), "source_key": "tally", "status": "ready"},
        )
        self.assertEqual(r.status_code, 409)
        self.client.delete(self.base + f"/devices/{self.device['id']}", headers=self.csrf)
        self.assertEqual(
            self.client.get(self.discovery + f"/runs/{run['id']}").json()["state"], "failed"
        )

    def test_dependent_gate_rejects_partial_unconfirmed_and_superseded_catalogs(self):
        from minkops_platform.discovery import require_ready
        from minkops_platform.errors import ServiceError

        run, body = self.start()
        self.collect(run)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            tenant = c.execute("SELECT id FROM tenants WHERE slug=%s", (self.slug,)).fetchone()
            with self.assertRaises(ServiceError):
                require_ready(c, tenant["id"], run["id"], ["tally"])
        self.client.post(self.discovery + f"/runs/{run['id']}/confirm", headers=self.csrf, json={})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            self.assertEqual(
                require_ready(c, tenant["id"], run["id"], ["tally"])["review"]["status"],
                "confirmed",
            )
            with self.assertRaises(ServiceError):
                require_ready(c, tenant["id"], run["id"], ["excel"])
        body["request_key"] = str(uuid.uuid4())
        self.client.post(self.discovery + "/runs", headers=self.csrf, json=body)
        with psycopg.connect(URL, row_factory=dict_row) as c, self.assertRaises(ServiceError):
            require_ready(c, tenant["id"], run["id"], ["tally"])
