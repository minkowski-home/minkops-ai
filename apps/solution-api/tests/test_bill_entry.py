"""MIN-117/118/119 integration against PostgreSQL and authenticated transport."""

import copy
import unittest
import uuid

import psycopg
import test_accounts_api as accounts_tests
from psycopg.rows import dict_row

URL = accounts_tests.URL


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class BillEntryTests(unittest.TestCase):
    setUp = accounts_tests.AccountsTests.setUp
    launch = accounts_tests.AccountsTests.launch
    execute_discovery = accounts_tests.AccountsTests.execute_discovery

    def test_both_mode_cannot_silently_fall_through_to_excel(self):
        response = self.client.post(self.base + '/runs', headers=self.csrf, json={
            'key': 'bill-entry', 'request_key': str(uuid.uuid4()),
            'file_ids': [self.upload_bill()], 'config': {'output_mode': 'both_in_place'},
        })
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn('combined verified write contract', response.text)

    def test_mock_policy_rejects_excel_both_and_preference_override(self):
        from minkops_platform.resources import REPOSITORY_ROOT
        from minkops_platform.solution_policy import bind_definition
        from minkops_platform.workflows import load_definition
        from psycopg.types.json import Jsonb

        definition = bind_definition(load_definition(REPOSITORY_ROOT / 'employees/accounts-desk/workflows/bill-entry'), 'mock-client')
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute("""UPDATE workflows SET config_schema=%s,
                config_values=jsonb_set(config_values,'{output_mode}','"tally_in_place"')
                WHERE key='bill-entry' AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant') RETURNING id,config_values""",
                (Jsonb(definition.tenant_schema),)).fetchone()
        bill = self.upload_bill()
        for mode in ('excel_in_place','both_in_place','draft_excel'):
            with self.subTest(mode=mode):
                response = self.client.post(self.base+'/runs',headers=self.csrf,json={
                    'key':'bill-entry','request_key':str(uuid.uuid4()),'file_ids':[bill],
                    'config':{'output_mode':mode},
                })
                self.assertEqual(response.status_code,422,response.text)
                response = self.client.patch(f"/api/tenants/mock-tenant/workflows/{row['id']}",headers=self.csrf,
                    json={'config_values':{**row['config_values'],'output_mode':mode}})
                self.assertEqual(response.status_code,422,response.text)

    def test_missing_vendor_holds_then_resumes_with_confirmed_new_master(self):
        discovery = self.tally_discovery('same-company')
        bill = self.upload_bill()
        run, _ = self.launch('bill-entry',file_ids=[bill],config={'output_mode':'tally_in_place','discovery_id':discovery})
        proposal = self.tally_result(run,bill)
        proposal['records'][0]['data']['vendor'] = 'New supplier'
        self.process(run,proposal)
        result = self.client.get(self.base+f"/runs/{run['id']}").json()['result']
        self.assertEqual(result['records'][0]['decision'],'hold')
        self.assertIn('New supplier',result['unresolved'][0]['reason'])
        reviewed = self.approve(run,result)
        self.assertEqual(reviewed['tally_writes'],[])
        new_discovery = self.tally_discovery('same-company',extra_ledgers=['New supplier'],reuse_device=True)
        response = self.client.post(self.base+f"/runs/{run['id']}/resolve-bill",headers=self.csrf,
            json={'file_id':bill,'user_input':'Supplier created. Use New supplier.','reject':False})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['config']['tally_target']['discovery_id'],new_discovery)
        with psycopg.connect(URL,row_factory=dict_row) as c:
            child=c.execute('SELECT config FROM account_runs WHERE parent_run_id=%s',(run['id'],)).fetchone()
            c.execute("UPDATE account_runs SET config=config || '{\"batch_finished_count\":0}'::jsonb WHERE id=%s",(run['id'],))
        self.assertEqual(child['config']['tally_target']['discovery_id'],new_discovery)
        from minkops_platform.accounts.batch import reconcile_once
        reconcile_once(URL)
        resumed = self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual(resumed['state'],'executing')

    def test_supplier_resume_cannot_change_tally_company_identity(self):
        discovery = self.tally_discovery('first-company')
        bill = self.upload_bill()
        run, _ = self.launch('bill-entry',file_ids=[bill],config={'output_mode':'tally_in_place','discovery_id':discovery})
        self.process(run,{'records':[],'findings':[], 'unresolved':[{'source_file_id':bill,'reason':'Supplier missing'}]})
        self.tally_discovery('replacement-company',reuse_device=True)
        response = self.client.post(self.base+f"/runs/{run['id']}/resolve-bill",headers=self.csrf,
            json={'file_id':bill,'user_input':'Continue','reject':False})
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('identity changed',response.text)

    def upload_bill(self, name="bill.pdf"):
        return self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"paths": f'["{name}"]'},
            files=[("files", (name, b"%PDF-1.4 test"))],
        ).json()["files"][0]["id"]

    def excel_result(self, bill, amount, invoice="A-1", operation="append"):
        return {
            "records": [
                {
                    "source_file_id": bill,
                    "destination_file_id": self.file_id,
                    "sheet": "Bills",
                    "operation": operation,
                    "data": {"Invoice": invoice, "Vendor": "Acme", "Amount": amount},
                    "evidence": [],
                    "findings": [],
                }
            ],
            "findings": [],
        }

    def process(self, run, result):
        from minkops_platform.accounts.worker import process

        with psycopg.connect(URL, row_factory=dict_row) as c:
            process(
                c,
                c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone(),
                executor=lambda *a, **k: copy.deepcopy(result),
            )

    def approve(self, run, result):
        r = self.client.post(
            self.base + f"/runs/{run['id']}/approve",
            headers=self.csrf,
            json={"result": result, "acknowledge_findings": True},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def tally_discovery(self, company_guid=None, *, extra_ledgers=(), reuse_device=False):
        self.native = "/api/tenants/mock-tenant/desktop"
        if not reuse_device:
            self.device = self.client.post(
                self.native + "/devices",
                headers=self.csrf,
                json={"name": "Bill PC", "installation_id": str(uuid.uuid4())},
            ).json()
        self.worker = {"Authorization": "Bearer " + self.device["credential"]}
        discovery = "/api/tenants/mock-tenant/discovery"
        categories = ["company", "ledgers", "voucher_types"]
        launched = self.client.post(
            discovery + "/runs",
            headers=self.csrf,
            json={
                "device_id": self.device["id"],
                "request_key": str(uuid.uuid4()),
                "config": {
                    "depth": "business_mappings",
                    "excel_source_ids": [],
                    "tally": {"company": "Test", "port": 9000, "categories": categories},
                },
            },
        )
        self.assertEqual(launched.status_code, 202, launched.text)
        claim = self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        names = {
            "company": ["Test"],
            "ledgers": ["Supplier", "Purchases", "Tax", *extra_ledgers],
            "voucher_types": ["Purchase"],
        }
        receipt = {
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
                                "category": k,
                                "status": "ready",
                                "count": len(names[k]),
                                "fields": ["NAME"],
                                "records": [{"NAME": v} for v in names[k]],
                            }
                            for k in categories
                        ],
                    },
                }
            ]
        }
        if company_guid:
            receipt["sources"][0]["snapshot"]["collections"][0]["records"][0]["GUID"] = company_guid
        r = self.client.post(
            f"/api/desktop/worker/jobs/{claim['id']}/finish",
            headers=self.worker,
            json={"claim_token": claim["claim_token"], "result": receipt},
        )
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post(
            discovery + f"/runs/{launched.json()['id']}/confirm", headers=self.csrf, json={}
        )
        self.assertEqual(r.status_code, 200, r.text)
        return launched.json()["id"]

    def tally_result(self, run, bill, total=118):
        data = {
            "invoice_number": "MOCK-1",
            "vendor": "Supplier",
            "date": "2026-10-01",
            "purchase_ledger": "Purchases",
            "subtotal": total - 18,
            "tax": 18,
            "tax_ledger": "Tax",
            "total": total,
            "cost_code": None,
        }
        return {
            "records": [
                {
                    "source_file_id": bill,
                    "destination_file_id": run["config"]["tally_target"]["discovery_id"],
                    "sheet": "Purchase",
                    "table": None,
                    "operation": "append",
                    "data": data,
                    "evidence": [
                        {"field": k, "page": 1, "quote": str(v)}
                        for k, v in data.items()
                        if v is not None
                    ],
                    "findings": [],
                }
            ],
            "findings": [],
        }

    def tally_job(self, run):
        payload = {
            "device_id": self.device["id"],
            "request_key": str(uuid.uuid4()),
            "operation": "tally.save",
            "input": {"run_id": run["id"], "write_id": run["tally_writes"][-1]["id"]},
        }
        r = self.client.post(self.native + "/jobs", headers=self.csrf, json=payload)
        self.assertEqual(r.status_code, 202, r.text)
        claim = self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        route = f"/api/desktop/worker/jobs/{claim['id']}"
        plan = self.client.get(
            route + "/plan?claim_token=" + claim["claim_token"], headers=self.worker
        )
        self.assertEqual(plan.status_code, 200, plan.text)
        return claim, route, plan.json()

    def current(self, plan, total=118):
        return {
            "master_id": "1",
            "guid": plan["remote_id"],
            "date": "20261001",
            "invoice_number": "MOCK-1",
            "vendor": "Supplier",
            "entries": [
                {"ledger": "Supplier", "amount": total * 100},
                {"ledger": "Purchases", "amount": -(total - 18) * 100},
                {"ledger": "Tax", "amount": -1800},
            ],
            "fingerprint": "a" * 64,
        }

    def test_tally_confirmation_approval_scoped_dispatch_and_exact_receipt_replay(self):
        discovery_id = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": discovery_id},
        )
        self.process(run, self.tally_result(run, bill))
        run = self.approve(run, self.tally_result(run, bill))
        self.assertEqual(run["state"], "writing")
        self.assertEqual(len(run["tally_writes"]), 1)
        claim, route, plan = self.tally_job(run)
        receipt = {
            "claim_token": claim["claim_token"],
            "result": {"outcome": "saved", "current": self.current(plan)},
        }
        bad = copy.deepcopy(receipt)
        bad["result"]["current"]["entries"][0]["amount"] += 1
        self.assertEqual(
            self.client.post(route + "/finish", headers=self.worker, json=bad).status_code, 409
        )
        for _ in range(2):
            r = self.client.post(route + "/finish", headers=self.worker, json=receipt)
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            self.client.get(self.base + f"/runs/{run['id']}").json()["state"], "completed"
        )
        repeat, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": discovery_id},
        )
        self.process(repeat, self.tally_result(repeat, bill))
        repeat = self.approve(repeat, self.tally_result(repeat, bill))
        _, _, replayed_plan = self.tally_job(repeat)
        self.assertEqual(replayed_plan["remote_id"], plan["remote_id"])

    def test_correction_handoff_preserves_old_snapshot_and_requires_explicit_edit(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        self.process(run, self.tally_result(run, bill))
        run = self.approve(run, self.tally_result(run, bill))
        claim, route, plan = self.tally_job(run)
        r = self.client.post(
            route + "/finish",
            headers=self.worker,
            json={
                "claim_token": claim["claim_token"],
                "result": {"outcome": "correction", "current": self.current(plan, 150)},
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        held = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(held["state"], "review")
        self.assertEqual(held["result"]["records"][0]["status"], "held")
        edited = held["result"]
        edited["records"][0]["operation"] = "update"
        resumed = self.approve(held, edited)
        _, _, correction = self.tally_job(resumed)
        self.assertEqual(correction["expected"]["fingerprint"], "a" * 64)

    def test_batch_failed_bill_does_not_discard_successful_sibling(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        good = self.upload_bill("good.pdf")
        bad = self.upload_bill("bad.pdf")
        root, _ = self.launch(
            "bill-entry",
            file_ids=[good, bad],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)
            ).fetchall()
        self.assertEqual(len(children), 2)
        successful = next(c for c in children if c["file_ids"] == [good])
        failed = next(c for c in children if c["file_ids"] == [bad])
        self.process(successful, self.tally_result(root, good))
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE account_runs SET state='failed',error='Unreadable scan' WHERE id=%s",
                (failed["id"],),
            )
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["state"], "review")
        self.assertEqual(len(loaded["result"]["records"]), 1)
        approved = self.approve(loaded, loaded["result"])
        self.assertEqual(approved["state"], "writing")
        self.assertEqual(len(approved["result"]["unresolved"]), 1)

    def test_excel_exact_repeat_skips_and_correction_can_resume_same_run(self):
        cat = self.execute_discovery()
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat)
        record = {
            "source_file_id": bill,
            "destination_file_id": self.file_id,
            "sheet": "Bills",
            "operation": "append",
            "data": {"Invoice": "A-1", "Vendor": "Acme", "Amount": 12},
            "evidence": [],
            "findings": [],
        }
        result = {"records": [record], "findings": []}
        self.process(run, result)
        done = self.approve(run, result)
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["writes"], [])
        self.assertEqual(done["result"]["records"][0]["status"], "duplicate")
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat)
        result["records"][0]["data"]["Amount"] = 24
        self.process(run, result)
        held = self.approve(run, result)
        self.assertEqual(held["state"], "review")
        edited = held["result"]
        edited["records"][0]["operation"] = "update"
        resumed = self.approve(held, edited)
        self.assertEqual(resumed["state"], "writing")

    def test_parallel_workers_keep_independent_bill_sessions_and_single_parent_task(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from unittest.mock import patch

        from minkops_platform.accounts.worker import STORE, work_once

        did = self.tally_discovery()
        ids = [self.upload_bill("one.pdf"), self.upload_bill("two.pdf")]
        root, _ = self.launch(
            "bill-entry",
            file_ids=ids,
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)
            ).fetchall()
        barrier = Barrier(2)

        def executor(key, files, context, on_event, **kwargs):
            self.assertEqual(len(context["config"]["file_ids"]), 1)
            barrier.wait(timeout=15)
            return self.tally_result(root, context["config"]["file_ids"][0])

        with (
            patch.object(STORE, "candidates", return_value=children),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            futures = [pool.submit(work_once, URL, executor=executor) for _ in range(2)]
            self.assertTrue(all(f.result(timeout=30) for f in futures))
        loaded = self.client.get(self.base + f"/tasks/{root['task_id']}/run").json()
        self.assertEqual(loaded["id"], root["id"])
        self.assertEqual(len(loaded["result"]["records"]), 2)

    def test_same_batch_duplicate_has_one_native_write_and_conflicting_version_is_held(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        ids = [self.upload_bill(f"bill-{i}.pdf") for i in range(3)]
        root, _ = self.launch(
            "bill-entry",
            file_ids=ids,
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s ORDER BY file_ids->>0",
                (root["id"],),
            ).fetchall()
        for i, child in enumerate(children):
            self.process(
                child, self.tally_result(root, child["file_ids"][0], 150 if i == 2 else 118)
            )
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        approved = self.approve(loaded, loaded["result"])
        self.assertEqual(len(approved["tally_writes"]), 1)
        self.assertEqual(
            [r["status"] for r in approved["result"]["records"]], ["writing", "writing", "held"]
        )
        claim, route, plan = self.tally_job(approved)
        done = self.client.post(
            route + "/finish",
            headers=self.worker,
            json={
                "claim_token": claim["claim_token"],
                "result": {"outcome": "saved", "current": self.current(plan)},
            },
        )
        self.assertEqual(done.status_code, 200, done.text)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(
            [r["status"] for r in loaded["result"]["records"]], ["saved", "duplicate", "held"]
        )
        self.assertEqual(loaded["state"], "review")

    def test_cancellation_late_tally_receipt_and_lease_expiry_do_not_replay_or_claim_success(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        self.process(run, self.tally_result(run, bill))
        approved = self.approve(run, self.tally_result(run, bill))
        claim, route, plan = self.tally_job(approved)
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE desktop_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",
                (claim["id"],),
            )
        self.assertIsNone(
            self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        )
        cancelled = self.client.post(
            self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(
            self.client.get(
                route + "/plan?claim_token=" + claim["claim_token"], headers=self.worker
            ).status_code,
            409,
        )
        late = self.client.post(
            route + "/finish",
            headers=self.worker,
            json={
                "claim_token": claim["claim_token"],
                "result": {"outcome": "saved", "current": self.current(plan)},
            },
        )
        self.assertEqual(late.status_code, 200, late.text)
        final = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(final["state"], "failed")
        self.assertIsNotNone(final["tally_writes"][0]["verified_at"])

    def test_human_clarification_retries_only_failed_bill_without_replaying_good_input(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        good, bad = self.upload_bill("good.pdf"), self.upload_bill("bad.pdf")
        root, _ = self.launch(
            "bill-entry",
            file_ids=[good, bad],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)
            ).fetchall()
        for child in children:
            proposal = (
                self.tally_result(root, good)
                if child["file_ids"] == [good]
                else {
                    "records": [],
                    "findings": [],
                    "unresolved": [{"source_file_id": bad, "reason": "Unreadable invoice number"}],
                }
            )
            self.process(child, proposal)
        reconcile_once(URL)
        ready = self.client.get(self.base + f"/runs/{root['id']}").json()
        approved = self.approve(ready, ready["result"])
        claim, route, plan = self.tally_job(approved)
        receipt = self.client.post(route + "/finish", headers=self.worker, json={
            "claim_token": claim["claim_token"],
            "result": {"outcome": "saved", "current": self.current(plan)},
        })
        self.assertEqual(receipt.status_code, 200, receipt.text)
        resumed = self.client.post(
            self.base + f"/runs/{root['id']}/resolve-bill",
            headers=self.csrf,
            json={"file_id": bad, "user_input": "Invoice number is MOCK-2. See page 2."},
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            retry = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s AND state='queued'",
                (root["id"],),
            ).fetchall()
        self.assertEqual(len(retry), 1)
        self.assertEqual(retry[0]["file_ids"], [bad])
        self.assertIn("MOCK-2", retry[0]["config"]["user_input"])
        result = self.tally_result(root, bad)
        result["records"][0]["data"]["invoice_number"] = "MOCK-2"
        self.process(retry[0], result)
        reconcile_once(URL)
        final = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(len(final["result"]["records"]), 2)
        self.assertEqual(final["result"]["unresolved"], [])
        saved = next(r for r in final["result"]["records"] if r["source_file_id"] == good)
        self.assertEqual(saved["status"], "saved")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            summary = c.execute("SELECT summary FROM tasks WHERE id=%s", (root["task_id"],)).fetchone()["summary"]
        self.assertEqual(summary, "1 bill entries ready; 0 bills need attention.")

    def test_pending_bill_reservation_holds_only_conflicting_intent(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        first, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        self.process(first, self.tally_result(first, bill))
        self.approve(first, self.tally_result(first, bill))
        second, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        self.process(second, self.tally_result(second, bill))
        held = self.approve(second, self.tally_result(second, bill))
        self.assertEqual(held["state"], "review")
        self.assertEqual(held["tally_writes"], [])
        self.assertEqual(held["result"]["records"][0]["status"], "held")

    def test_excel_correction_rechecks_values_changed_by_another_verified_run(self):
        cat = self.execute_discovery()
        bill = self.upload_bill()
        first, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat)
        self.process(first, self.excel_result(bill, 24))
        second, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat)
        self.process(second, self.excel_result(bill, 13))
        updated = self.approve(second, self.excel_result(bill, 13, operation="update"))
        write = updated["writes"][0]
        route = self.base + f"/runs/{second['id']}/writes/{write['id']}"
        saved = self.client.get(route + "/content").content
        response = self.client.post(
            route + "/verify", headers=self.csrf, files={"file": ("records.xlsx", saved)}
        )
        self.assertEqual(response.status_code, 200, response.text)
        held = self.approve(first, self.excel_result(bill, 24, operation="update"))
        self.assertEqual(held["state"], "review")
        self.assertEqual(held["writes"], [])
        self.assertEqual(held["result"]["records"][0]["current_excel"]["Amount"], 13)
        resumed = self.approve(held, held["result"])
        self.assertEqual(resumed["state"], "writing")

    def test_late_cancelled_excel_receipt_retains_newer_observed_source_bytes(self):
        from io import BytesIO

        from openpyxl import load_workbook

        cat = self.execute_discovery()
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat)
        result = self.excel_result(bill, 24, invoice="A-2")
        self.process(run, result)
        approved = self.approve(run, result)
        write = approved["writes"][0]
        route = self.base + f"/runs/{run['id']}/writes/{write['id']}"
        saved = self.client.get(route + "/content").content
        response = self.client.post(
            self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf
        )
        self.assertEqual(response.status_code, 200, response.text)
        book = load_workbook(BytesIO(saved))
        book["Bills"]["C2"] = 33
        current = BytesIO()
        book.save(current)
        refresh = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"source_id": self.source["id"], "writable": "true", "paths": '["records.xlsx"]'},
            files=[("files", ("records.xlsx", current.getvalue()))],
        )
        self.assertEqual(refresh.status_code, 200, refresh.text)
        for _ in range(2):
            receipt = self.client.post(
                route + "/verify", headers=self.csrf, files={"file": ("records.xlsx", saved)}
            )
            self.assertEqual(receipt.status_code, 200, receipt.text)
            self.assertEqual(receipt.json()["state"], "failed")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            actual = c.execute(
                "SELECT id,content FROM account_files WHERE source_id=%s AND current",
                (self.source["id"],),
            ).fetchone()
        self.assertEqual(str(actual["id"]), refresh.json()["files"][0]["id"])
        self.assertEqual(bytes(actual["content"]), current.getvalue())

    def test_rejected_failed_input_does_not_reappear_when_another_bill_is_clarified(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        ids = [self.upload_bill(f"failed-{i}.pdf") for i in range(2)]
        root, _ = self.launch(
            "bill-entry",
            file_ids=ids,
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE account_runs SET state='failed',error='Unreadable' WHERE parent_run_id=%s",
                (root["id"],),
            )
        reconcile_once(URL)
        route = self.base + f"/runs/{root['id']}/resolve-bill"
        rejected = self.client.post(
            route, headers=self.csrf, json={"file_id": ids[0], "reject": True}
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        retry = self.client.post(
            route,
            headers=self.csrf,
            json={"file_id": ids[1], "user_input": "Retry this bill only."},
        )
        self.assertEqual(retry.status_code, 200, retry.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            child = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s AND state='queued'",
                (root["id"],),
            ).fetchone()
        self.process(child, self.tally_result(root, ids[1]))
        reconcile_once(URL)
        final = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(final["result"]["unresolved"], [])
        self.assertEqual(len(final["result"]["records"]), 1)

    def test_same_observed_company_on_two_pcs_shares_pending_bill_reservation(self):
        guid = str(uuid.uuid4())
        did = self.tally_discovery(guid)
        first_device, first_worker = self.device, self.worker
        bill = self.upload_bill()
        first, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        self.process(first, self.tally_result(first, bill))
        first = self.approve(first, self.tally_result(first, bill))
        did = self.tally_discovery(guid)
        second_device, second_worker = self.device, self.worker
        second, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        self.process(second, self.tally_result(second, bill))
        held = self.approve(second, self.tally_result(second, bill))
        self.assertEqual(held["tally_writes"], [])
        self.device, self.worker = first_device, first_worker
        claim, route, first_plan = self.tally_job(first)
        response = self.client.post(
            route + "/finish",
            headers=self.worker,
            json={
                "claim_token": claim["claim_token"],
                "result": {"outcome": "saved", "current": self.current(first_plan)},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.device, self.worker = second_device, second_worker
        resumed = self.approve(held, held["result"])
        _, _, second_plan = self.tally_job(resumed)
        self.assertEqual(first_plan["remote_id"], second_plan["remote_id"])
