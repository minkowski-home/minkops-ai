"""Metadata context and live references have separate authorization and lifetimes."""

import unittest
import os
from unittest.mock import patch

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

    def test_hosted_dispatch_reads_committed_launch_after_response(self):
        discovery = self.tally_discovery("company-1", schema=True)
        bill = self.upload_bill()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL")
        calls = []

        def dispatched():
            with psycopg.connect(URL) as c:
                calls.append(
                    c.execute(
                        "SELECT count(*) FROM workflow_runs WHERE config->'tally_target'->>'discovery_id'=%s",
                        (discovery,),
                    ).fetchone()[0]
                )

        with (
            patch.dict(
                os.environ,
                {"WORKER_JOB_RESOURCE": "projects/test/locations/us-central1/jobs/worker"},
            ),
            patch("minkops_connectors.cloud_run.run_job", dispatched),
        ):
            self.launch(
                "bill-entry",
                file_ids=[bill],
                config={"output_mode": "tally_in_place", "discovery_id": discovery},
            )
        self.assertEqual(calls, [1])

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

    def test_reference_readiness_wakes_after_initial_generation_was_acknowledged(self):
        from minkops_platform.runtime.store import WorkflowRunStore

        created = []

        def cleanup():
            # Leave no queued runs in the shared disposable database's bounded
            # candidate window; subsequent tests must not inherit this backlog.
            with psycopg.connect(URL) as c:
                c.execute("UPDATE workflow_runs SET state='failed' WHERE id=ANY(%s::uuid[])", (created,))

        self.addCleanup(cleanup)
        for failed in (False, True):
            with self.subTest(failed=failed):
                discovery = self.tally_discovery("company-1", schema=True, reuse_device=failed)
                run, _ = self.launch("bill-entry", file_ids=[self.upload_bill()],
                                     config={"output_mode": "tally_in_place", "discovery_id": discovery})
                created.append(run["id"])
                with psycopg.connect(URL, row_factory=dict_row) as c:
                    self.assertNotIn(run["id"], [str(r["id"]) for r in WorkflowRunStore().candidates(c)])
                    c.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL")
                calls = []

                def dispatched():
                    with psycopg.connect(URL, row_factory=dict_row) as c:
                        calls.append([str(r["id"]) for r in WorkflowRunStore().candidates(c)])

                with (patch.dict(os.environ, {"WORKER_JOB_RESOURCE": "projects/test/locations/us-central1/jobs/worker"}),
                      patch("minkops_connectors.cloud_run.run_job", dispatched)):
                    if failed:
                        job = self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
                        response = self.client.post(f"/api/desktop/worker/jobs/{job['id']}/finish", headers=self.worker,
                                                    json={"claim_token": job["claim_token"], "result": None, "error": "Tally offline"})
                    else:
                        response = self.finish_references()
                    self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(calls), 1)
                if failed:
                    detail = self.client.get(f"/api/tenants/mock-tenant/accounts/runs/{run['id']}").json()
                    self.assertEqual(detail["state"], "failed")
                else:
                    self.assertIn(run["id"], calls[0])

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
