"""Metadata context and live references have separate authorization and lifetimes."""

import unittest

import psycopg
from psycopg.rows import dict_row
import test_bill_entry as bills
import test_accounts_api as accounts

URL = accounts.URL


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class SchemaContextTests(unittest.TestCase):
    setUp = accounts.AccountsTests.setUp
    launch = accounts.AccountsTests.launch
    tally_discovery = bills.BillEntryTests.tally_discovery
    upload_bill = bills.BillEntryTests.upload_bill
    process = bills.BillEntryTests.process
    tally_result = bills.BillEntryTests.tally_result

    def finish_references(self, receipt=None):
        claim = self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        self.assertEqual(claim["operation"], "tally.references")
        plan = self.client.get(
            f"/api/desktop/worker/jobs/{claim['id']}/plan?claim_token={claim['claim_token']}",
            headers=self.worker,
        )
        self.assertEqual(plan.status_code, 200, plan.text)
        self.assertEqual(plan.json()["categories"], ["company", "ledgers", "voucher_types"])
        body = {"claim_token": claim["claim_token"], "result": receipt or self.reference_receipt}
        route = f"/api/desktop/worker/jobs/{claim['id']}/finish"
        done = self.client.post(route, headers=self.worker, json=body)
        if done.status_code == 200 and done.json()["state"] == "completed":
            self.assertEqual(
                self.client.post(route, headers=self.worker, json=body).status_code, 200
            )
            self.assertEqual(done.json()["result"], {"references_prepared": True})
        return done

    def test_schema_run_waits_for_pc_before_paid_execution_and_pins_live_references(self):
        from minkops_platform.runtime.store import WorkflowRunStore

        discovery = self.tally_discovery("company-1", schema=True)
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            self.assertNotIn(run["id"], [str(r["id"]) for r in WorkflowRunStore().candidates(c)])
        self.assertEqual(self.finish_references().status_code, 200)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            ready = c.execute("SELECT * FROM workflow_runs WHERE id=%s", (run["id"],)).fetchone()
            self.assertEqual(
                ready["config"]["tally_target"]["references"]["company_guid"], "company-1"
            )
            self.assertIn(run["id"], [str(r["id"]) for r in WorkflowRunStore().candidates(c)])
            from minkops_platform.accounts.handlers import BillHandler

            _, context, _ = BillHandler().prepare(c, ready)
            self.assertEqual(context["source_catalog"]["run_id"], discovery)
            self.assertEqual(
                context["source_catalog"]["sources"][0]["snapshot"]["schema_tables"][1]["table"],
                "Ledger",
            )
            catalog = c.execute(
                "SELECT catalog FROM discovery_runs WHERE id=%s", (discovery,)
            ).fetchone()["catalog"]
            self.assertTrue(
                all(not col["records"] for col in catalog["sources"][0]["snapshot"]["collections"])
            )

    def test_schema_retry_fetches_current_supplier_but_rejects_company_replacement(self):
        discovery = self.tally_discovery("company-1", schema=True)
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        self.assertEqual(self.finish_references().status_code, 200)
        self.process(
            run,
            {
                "records": [],
                "findings": [],
                "unresolved": [{"source_file_id": bill, "reason": "Supplier missing"}],
            },
        )
        refreshed = self.tally_discovery("company-2", schema=True, reuse_device=True)
        response = self.client.post(
            self.base + f"/runs/{run['id']}/resolve-bill",
            headers=self.csrf,
            json={"file_id": bill, "user_input": "Supplier added, continue", "reject": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            child = c.execute(
                "SELECT config FROM workflow_runs WHERE parent_run_id=%s AND NOT COALESCE((config->>'superseded')::boolean,false)",
                (run["id"],),
            ).fetchone()
            self.assertEqual(child["config"]["source_catalog_snapshot"]["run_id"], refreshed)
        rejected = self.finish_references()
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["state"], "failed")
        self.assertIn("identity changed", rejected.text)
        self.assertIsNone(
            self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        )
