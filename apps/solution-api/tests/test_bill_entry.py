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

    def test_master_references_canonicalize_before_automatic_write_and_keep_native_contract(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        proposal = self.tally_result(run, bill)
        proposal["records"][0]["data"].update(vendor="sup plier", purchase_ledger=None, tax_ledger=None)
        self.process(run, proposal)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"], "writing", loaded.get("result"))
        self.assertEqual(loaded["result"]["records"][0]["data"]["vendor"], "Supplier")
        _, _, plan = self.tally_job(loaded)
        self.assertEqual(plan["data"]["purchase_ledger"], "Purchases")
        self.assertEqual(plan["data"]["tax_ledger"], "Tax")
        self.assertNotIn("master_refs", plan)

    def test_exception_only_batch_does_not_require_approval_for_clean_sibling(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery()
        inputs = [self.upload_bill("clean.pdf"), self.upload_bill("uncertain.pdf")]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)).fetchall()
        for child in children:
            proposal = self.tally_result(root, child["file_ids"][0])
            if child["file_ids"][0] == inputs[1]:
                proposal["records"][0]["master_refs"]["vendor"]["ref"] = "foreign-catalog"
            self.process(child, proposal)
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["state"], "writing")
        self.assertEqual(len(loaded["tally_writes"]), 1)
        self.assertEqual(loaded["result"]["unresolved"][0]["source_file_id"], inputs[1])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            waiting = c.execute("SELECT summary FROM task_events WHERE task_id=%s ORDER BY id DESC LIMIT 1",
                                (root["task_id"],)).fetchone()["summary"]
        # An offline PC leaves saves queued; the status names the PC to start.
        self.assertIn(self.device["name"], waiting)
        self.assertIn("Keep Minkops running", waiting)

    def test_run_list_is_a_bounded_summary_without_pinned_snapshots(self):
        did = self.tally_discovery()
        bill = self.upload_bill("listed.pdf")
        run, _ = self.launch("bill-entry", file_ids=[bill], config={"output_mode": "tally_in_place", "discovery_id": did})
        self.process(run, self.tally_result(run, bill))
        listed = self.client.get(self.base + "/runs")
        self.assertEqual(listed.status_code, 200, listed.text)
        summary = next(r for r in listed.json() if r["id"] == run["id"])
        # Full runs pin multi-megabyte catalog snapshots; a list must not repeat them.
        self.assertNotIn("config", summary)
        self.assertNotIn("result", summary)
        self.assertEqual((summary["task_id"], summary["state"], summary["records"], summary["unresolved"]),
                         (run["task_id"], "review", 1, 0))

    def test_stopping_a_batch_opens_one_attention_item_per_read_bill(self):
        did = self.tally_discovery()
        inputs = [self.upload_bill(f"stop-{i}.pdf") for i in range(3)]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "all_outputs"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = {c_["file_ids"][0]: c_ for c_ in c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],))}
        # Two bills are read; the third is still waiting when the operator stops.
        self.process(children[inputs[0]], self.tally_result(root, inputs[0]))
        held = self.tally_result(root, inputs[1])
        held["records"][0]["master_refs"]["vendor"]["ref"] = "foreign-catalog"
        self.process(children[inputs[1]], held)
        stop = self.client.post(f"/api/tenants/mock-tenant/tasks/{root['task_id']}/control",
                                headers=self.csrf, json={"action": "stop"})
        self.assertEqual(stop.status_code, 200, stop.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            keys = [r["event_key"] for r in c.execute(
                "SELECT event_key FROM attention_items WHERE task_id=%s ORDER BY event_key", (root["task_id"],))]
        self.assertEqual(keys, sorted(f"bill:{root['id']}:{f}:bill" for f in inputs[:2]))

    def exception_only_batch(self, count=2):
        did = self.tally_discovery()
        inputs = [self.upload_bill(f"bill-{i}.pdf") for i in range(count)]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)).fetchall()
        return root, inputs, children

    def numbered_result(self, run, bill, invoice):
        result = self.tally_result(run, bill)
        result["records"][0]["data"]["invoice_number"] = invoice
        for evidence in result["records"][0]["evidence"]:
            if evidence["field"] == "invoice_number":
                evidence["quote"] = invoice
        return result

    def test_unavailable_destination_pc_holds_clean_bills_for_retry(self):
        from minkops_platform.accounts.batch import reconcile_once
        root, inputs, children = self.exception_only_batch()
        for child in children:
            self.process(child, self.numbered_result(root, child["file_ids"][0], f"PC-{child['file_ids'][0]}"))
        disconnected = self.client.delete(f"{self.native}/devices/{self.device['id']}", headers=self.csrf)
        self.assertEqual(disconnected.status_code, 200, disconnected.text)
        reconcile_once(URL)  # Must not raise into the shared worker loop.
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["state"], "review")
        self.assertEqual(loaded["tally_writes"], [])
        for record in loaded["result"]["records"]:
            self.assertEqual(record["status"], "held")
            self.assertIn("PC is unavailable", record["save_hold"])

    def test_retry_save_after_reconnecting_an_unavailable_pc(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        self.client.delete(f"{self.native}/devices/{self.device['id']}", headers=self.csrf)
        self.process(run, self.tally_result(run, bill))
        held = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual((held["state"], held["result"]["records"][0]["status"]), ("review", "held"))
        offline = self.client.post(f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}",
                                   headers=self.csrf, json={"action": "retry_save"})
        self.assertEqual(offline.status_code, 409, offline.text)
        self.device = self.client.post(self.native + "/devices", headers=self.csrf, json={
            "name": "Bill PC", "installation_id": self.device["installation_id"]}).json()
        self.worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.7.0"}
        retried = self.decide(run, bill, "retry_save")
        self.assertEqual(retried["state"], "writing")
        self.save_receipt(retried, "MOCK-1")
        self.assertEqual(self.client.get(self.base + f"/runs/{run['id']}").json()["state"], "completed")

    def test_batch_reconciliation_isolates_an_unexpected_parent_failure(self):
        from unittest import mock

        from minkops_platform.accounts import batch, tally_writes
        broken, _, broken_children = self.exception_only_batch()
        healthy, _, healthy_children = self.exception_only_batch()
        for root, children in ((broken, broken_children), (healthy, healthy_children)):
            for child in children:
                self.process(child, self.numbered_result(root, child["file_ids"][0], f"ISO-{child['file_ids'][0]}"))
        real = tally_writes.prepare_automatic

        def flaky(connection, run, result):
            if str(run["id"]) == broken["id"]:
                raise RuntimeError("unexpected aggregation defect")
            return real(connection, run, result)

        with mock.patch.object(tally_writes, "prepare_automatic", flaky):
            for _ in range(batch.AGGREGATION_ATTEMPTS):
                batch.reconcile_once(URL)
        self.assertEqual(self.client.get(self.base + f"/runs/{healthy['id']}").json()["state"], "writing")
        failed = self.client.get(self.base + f"/runs/{broken['id']}").json()
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["tally_writes"], [])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            diagnostic = c.execute(
                "SELECT details FROM workflow_run_diagnostics WHERE run_id=%s AND event_type='batch.aggregation_failed'",
                (broken["id"],),
            ).fetchone()
            item = c.execute("SELECT status FROM attention_items WHERE event_key=%s", (f"run:{broken['id']}",)).fetchone()
        self.assertEqual(diagnostic["details"]["error_type"], "RuntimeError")
        self.assertEqual(item["status"], "pending")

    def decide(self, run, bill, action):
        response = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}",
            headers=self.csrf, json={"action": action},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def save_receipt(self, run, invoice, error=None):
        claim, route, plan = self.tally_job(run)
        current = {**self.current(plan), "invoice_number": invoice}
        response = self.client.post(route + "/finish", headers=self.worker, json={
            "claim_token": claim["claim_token"],
            **({"error": error} if error else {"result": {"outcome": "saved", "current": current}})})
        self.assertEqual(response.status_code, 200, response.text)

    def guess_then_recheck_sibling(self, save_error=None):
        """Best-guess one unresolved bill, then recheck a failed sibling."""
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        guessed, failed = self.upload_bill("guess.pdf"), self.upload_bill("failed.pdf")
        root, _ = self.launch("bill-entry", file_ids=[guessed, failed], config={
            "output_mode": "tally_in_place", "discovery_id": did})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = {r["file_ids"][0]: r for r in c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)).fetchall()}
            c.execute("UPDATE account_runs SET state='failed',error='Unreadable' WHERE id=%s",
                      (children[failed]["id"],))
        proposal = self.numbered_result(root, guessed, "GUESS-1")
        proposal["records"][0]["exceptions"] = [
            {"code": "classification_uncertain", "detail": "Expense ledger is a best guess."}]
        proposal["unresolved"] = [{"source_file_id": guessed, "code": "classification_uncertain",
                                   "reason": "Expense ledger is a best guess."}]
        self.process(children[guessed], proposal)
        reconcile_once(URL)
        self.save_receipt(self.decide(root, guessed, "guess"), "GUESS-1", save_error)
        self.decide(root, failed, "retry")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            retry = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s AND state='queued'",
                              (root["id"],)).fetchone()
        self.process(retry, self.numbered_result(root, failed, "RETRY-1"))
        reconcile_once(URL)
        return root, guessed, failed, self.client.get(self.base + f"/runs/{root['id']}").json()

    def test_saved_best_guess_stays_resolved_when_a_sibling_is_rechecked(self):
        root, _, failed, loaded = self.guess_then_recheck_sibling()
        self.assertEqual(loaded["result"]["unresolved"], [], loaded["result"])
        self.save_receipt(self.decide(root, failed, "guess"), "RETRY-1")
        self.assertEqual(self.client.get(self.base + f"/runs/{root['id']}").json()["state"], "completed")

    def test_do_nothing_defers_input_without_blocking_exception_only_saves(self):
        from minkops_platform.accounts.batch import reconcile_once

        root, inputs, _ = self.exception_only_batch()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE account_runs SET state='failed',error='Unreadable' WHERE parent_run_id=%s",
                      (root["id"],))
        reconcile_once(URL)
        self.decide(root, inputs[0], "nothing")
        self.decide(root, inputs[1], "retry")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            retry = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s AND state='queued'",
                              (root["id"],)).fetchone()
        self.process(retry, self.numbered_result(root, inputs[1], "AFTER-DEFER"))
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["state"], "writing", loaded["result"])
        self.assertEqual(len(loaded["tally_writes"]), 1)
        self.assertEqual(loaded["result"]["findings"], [])
        self.assertEqual(loaded["result"]["deferred"], [{"source_file_id": inputs[0]}])

    def test_notes_never_hold_exception_only_bills_but_coded_exceptions_reach_attention(self):
        from minkops_platform.accounts.batch import reconcile_once

        root, inputs, children = self.exception_only_batch()
        for child in children:
            file_id = child["file_ids"][0]
            proposal = self.numbered_result(root, file_id, f"NOTE-{file_id}")
            if file_id == inputs[0]:
                # Observations that previously became blocking findings.
                proposal["records"][0]["notes"] = [
                    "Subtotal plus tax reconciles.", "Optional cost code absent.",
                    "Resembles DEMO26-C1-B1; the native duplicate check decides."]
            else:
                proposal["records"][0]["exceptions"] = [{
                    "code": "classification_uncertain",
                    "detail": "Office Maintenance and Site Services both fit this purchase."}]
            self.process(child, proposal)
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        records = {r["source_file_id"]: r for r in loaded["result"]["records"]}
        self.assertEqual((records[inputs[0]]["status"], records[inputs[0]]["findings"]), ("writing", []))
        self.assertEqual(records[inputs[1]]["decision"], "hold")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            item = c.execute("SELECT label,status FROM attention_items WHERE event_key=%s",
                             (f"bill:{root['id']}:{inputs[1]}:bill",)).fetchone()
        self.assertEqual((item["label"], item["status"]), ("Ledger unclear", "pending"))

    def test_each_bill_in_a_multi_bill_file_gets_its_own_decision(self):
        did = self.tally_discovery()
        bill = self.upload_bill("statement.pdf")
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        proposal = self.numbered_result(run, bill, "MULTI-1")
        second = copy.deepcopy(self.numbered_result(run, bill, "MULTI-2")["records"][0])
        second["exceptions"] = [{"code": "classification_uncertain", "detail": "Two ledgers fit."}]
        proposal["records"].append(second)
        self.process(run, proposal)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.save_receipt(loaded, "MULTI-1")
        item_key = f"bill:{run['id']}:{bill}:bill"
        with psycopg.connect(URL, row_factory=dict_row) as c:
            item = c.execute("SELECT status FROM attention_items WHERE event_key=%s", (item_key,)).fetchone()
        self.assertEqual(item["status"], "pending")  # The second bill still needs a decision.
        route = f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}"
        self.assertEqual(self.client.post(route, headers=self.csrf, json={"action": "guess", "proposal": 0}).status_code, 409)
        self.assertEqual(self.client.post(route, headers=self.csrf, json={"action": "guess", "proposal": 7}).status_code, 422)
        decided = self.client.post(route, headers=self.csrf, json={"action": "guess", "proposal": 1})
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertEqual(len(decided.json()["tally_writes"]), 2)
        self.save_receipt(decided.json(), "MULTI-2")
        final = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(final["state"], "completed")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            items = {r["kind"]: r["status"] for r in c.execute(
                "SELECT kind,status FROM attention_items WHERE task_id=%s", (run["task_id"],))}
        self.assertEqual(items, {"bill": "done", "review": "pending"})

    def test_bill_before_the_company_books_is_held_before_any_import(self):
        did = self.tally_discovery(books_from="20261005")
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        self.assertEqual(run["config"]["tally_target"]["companies"][0]["books_from"], "2026-10-05")
        self.process(run, self.tally_result(run, bill))  # Bill dated 2026-10-01.
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual((loaded["state"], loaded["tally_writes"]), ("review", []))
        self.assertIn("before Test's books begin on 2026-10-05", loaded["result"]["records"][0]["findings"][0])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            item = c.execute("SELECT label FROM attention_items WHERE event_key=%s",
                             (f"bill:{run['id']}:{bill}:bill",)).fetchone()
        self.assertEqual(item["label"], "Before books begin")

    def test_recheck_does_not_restore_an_issue_the_operator_already_decided(self):
        _, guessed, _, loaded = self.guess_then_recheck_sibling("Tally rejected the voucher date.")
        record = next(r for r in loaded["result"]["records"] if r["source_file_id"] == guessed)
        self.assertEqual(record["status"], "held")
        self.assertNotIn(guessed, [i["source_file_id"] for i in loaded["result"]["unresolved"]])

    def split_result(self, run, bill, amounts=(9,9)):
        result=self.tally_result(run,bill)
        record=result["records"][0]
        record["data"]["tax_ledger"]=None
        record["master_refs"]["tax_ledger"]=None
        target=run["config"]["tally_target"]["companies"][0]
        refs={v["name"]:k for k,v in target["ledger_refs"].items()}
        record["tax_allocations"]=[{"ref":refs[name],"amount":amount,"evidence":"Printed tax component matches native definition."}
                                   for name,amount in zip(("Tax","SGST"),amounts)]
        return result

    def test_split_tax_native_plan_and_receipt_cannot_collapse_components(self):
        did=self.tally_discovery(extra_ledgers=("SGST",))
        bill=self.upload_bill()
        run,_=self.launch("bill-entry",file_ids=[bill],config={"output_mode":"tally_in_place","discovery_id":did,"review_mode":"only_exceptions"})
        self.process(run,self.split_result(run,bill))
        loaded=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"],"writing",loaded.get("result"))
        claim,route,plan=self.tally_job(loaded)
        for version in ("1","2"):
            legacy=self.client.get(route+'/plan?claim_token='+claim["claim_token"],headers={**self.worker,"X-Minkops-Plan-Version":version})
            self.assertEqual(legacy.status_code,409,legacy.text)
            self.assertIn("Update Minkops",legacy.json()["detail"])
        self.assertEqual(plan["format_version"],3)
        self.assertEqual(plan["references"]["voucher_type"]["NAME"],"Purchase")
        self.assertEqual(plan["tax_allocations"],[{"ledger":"Tax","amount":9},{"ledger":"SGST","amount":9}])
        receipt=self.current(plan)
        rejected=self.client.post(route+'/finish',headers=self.worker,json={"claim_token":claim["claim_token"],"result":{"outcome":"saved","current":receipt}})
        self.assertEqual(rejected.status_code,409,rejected.text)
        receipt["entries"]=[*receipt["entries"][:2],{"ledger":"Tax","amount":-900},{"ledger":"SGST","amount":-900}]
        accepted=self.client.post(route+'/finish',headers=self.worker,json={"claim_token":claim["claim_token"],"result":{"outcome":"saved","current":receipt}})
        self.assertEqual(accepted.status_code,200,accepted.text)

    def test_conflicting_splits_with_identical_totals_hold_both_before_dispatch(self):
        from minkops_platform.accounts.batch import reconcile_once
        did=self.tally_discovery(extra_ledgers=("SGST",))
        bills=[self.upload_bill("one.pdf"),self.upload_bill("two.pdf")]
        root,_=self.launch("bill-entry",file_ids=bills,config={"output_mode":"tally_in_place","discovery_id":did,"review_mode":"only_exceptions"})
        with psycopg.connect(URL,row_factory=dict_row) as c:
            children=c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s ORDER BY file_ids->>0",(root["id"],)).fetchall()
        for child,amounts in zip(children,((9,9),(8,10))):self.process(child,self.split_result(root,child["file_ids"][0],amounts))
        reconcile_once(URL)
        loaded=self.client.get(self.base+f"/runs/{root['id']}").json()
        self.assertEqual(loaded["tally_writes"],[])
        self.assertTrue(all(r.get("status")=="held" for r in loaded["result"]["records"]))

    def test_child_wide_findings_hold_only_that_input(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery()
        inputs = [self.upload_bill("clean.pdf"), self.upload_bill("uncertain.pdf")]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)).fetchall()
        for child in children:
            proposal = self.tally_result(root, child["file_ids"][0])
            if child["file_ids"][0] == inputs[1]:
                proposal["exceptions"] = [{"code": "source_values_conflict",
                                           "detail": "This input has contradictory source evidence."}]
            self.process(child, proposal)
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["state"], "writing")
        self.assertEqual(len(loaded["tally_writes"]), 1)
        self.assertEqual(loaded["result"]["findings"], [])
        records = {r["source_file_id"]: r for r in loaded["result"]["records"]}
        self.assertEqual(records[inputs[0]]["status"], "writing")
        self.assertEqual(records[inputs[1]]["decision"], "hold")
        self.assertIn("contradictory", records[inputs[1]]["findings"][0])

    def test_destination_pc_scopes_discovery_and_pins_bill_jobs(self):
        first = self.tally_discovery("first-company")
        first_pc = self.device["id"]
        second = self.tally_discovery("second-company")
        second_pc = self.device["id"]
        endpoint = "/api/tenants/mock-tenant/discovery/latest"
        self.assertEqual(self.client.get(endpoint).json()["id"], second)
        response = self.client.get(endpoint, params={"device_id": first_pc})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], first)
        run, _ = self.launch(
            "bill-entry", file_ids=[self.upload_bill()], destination_device_id=first_pc,
            config={"output_mode": "tally_in_place", "discovery_id": first},
        )
        self.assertEqual(run["config"]["destination_device_id"], first_pc)
        self.assertEqual(run["config"]["tally_target"]["device_id"], first_pc)
        self.process(run, self.tally_result(run, run["file_ids"][0]))
        proposal = self.client.get(self.base + f"/runs/{run['id']}").json()["result"]
        self.approve(run, proposal)
        with psycopg.connect(URL) as connection:
            queued_pc = connection.execute(
                "SELECT device_id FROM desktop_jobs WHERE task_id=%s AND operation='tally.save'",
                (run["task_id"],),
            ).fetchone()[0]
        self.assertEqual(str(queued_pc), first_pc)
        rejected = self.client.post(self.base + "/runs", headers=self.csrf, json={
            "key": "bill-entry", "request_key": str(uuid.uuid4()),
            "file_ids": [self.upload_bill()], "destination_device_id": second_pc,
            "config": {"output_mode": "tally_in_place", "discovery_id": first},
        })
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertIn("selected destination PC", rejected.text)

    def test_destination_pc_never_falls_back_or_accepts_revoked_devices(self):
        self.tally_discovery("ready-company")
        selected_pc = self.device["id"]
        empty_pc = self.client.post("/api/tenants/mock-tenant/desktop/devices", headers=self.csrf,
            json={"name": "No discovery yet", "installation_id": str(uuid.uuid4())}).json()["id"]
        endpoint = "/api/tenants/mock-tenant/discovery/latest"
        self.assertIsNone(self.client.get(endpoint, params={"device_id": empty_pc}).json())
        unknown = self.client.get(endpoint, params={"device_id": str(uuid.uuid4())})
        self.assertEqual(unknown.status_code, 404, unknown.text)
        self.client.delete(f"/api/tenants/mock-tenant/desktop/devices/{selected_pc}", headers=self.csrf)
        response = self.client.get(endpoint, params={"device_id": selected_pc})
        self.assertEqual(response.status_code, 409, response.text)

    def test_excel_destination_cannot_cross_pc_folder_bindings(self):
        catalog = self.execute_discovery()
        pc = self.client.post("/api/tenants/mock-tenant/desktop/devices", headers=self.csrf,
            json={"name": "Excel PC", "installation_id": str(uuid.uuid4())}).json()["id"]
        other = self.client.post("/api/tenants/mock-tenant/desktop/devices", headers=self.csrf,
            json={"name": "Other PC", "installation_id": str(uuid.uuid4())}).json()["id"]
        bound = self.client.post(f"/api/tenants/mock-tenant/desktop/devices/{pc}/sources/{self.source['id']}", headers=self.csrf)
        self.assertEqual(bound.status_code, 200, bound.text)
        run, _ = self.launch("bill-entry", file_ids=[self.upload_bill()], catalog_id=catalog,
            destination_device_id=pc, config={"output_mode": "excel_in_place"})
        self.assertEqual(run["config"]["destination_device_id"], pc)
        rejected = self.client.post(self.base + "/runs", headers=self.csrf, json={
            "key": "bill-entry", "request_key": str(uuid.uuid4()), "file_ids": [self.upload_bill()],
            "catalog_id": catalog, "destination_device_id": other, "config": {"output_mode": "excel_in_place"},
        })
        self.assertEqual(rejected.status_code, 404, rejected.text)
        self.assertIn("original folder", rejected.text)
        bill = run["file_ids"][0]
        result = self.excel_result(bill, 24, invoice="A-2")
        self.process(run, result)
        moved = self.client.post(f"/api/tenants/mock-tenant/desktop/devices/{other}/sources/{self.source['id']}", headers=self.csrf)
        self.assertEqual(moved.status_code, 200, moved.text)
        rejected = self.client.post(self.base + f"/runs/{run['id']}/approve", headers=self.csrf,
            json={"result": result, "acknowledge_findings": True})
        self.assertEqual(rejected.status_code, 404, rejected.text)
        with psycopg.connect(URL) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM account_writes WHERE run_id=%s", (run["id"],)).fetchone()[0], 0)


    def test_both_mode_cannot_silently_fall_through_to_excel(self):
        response = self.client.post(
            self.base + "/runs",
            headers=self.csrf,
            json={
                "key": "bill-entry",
                "request_key": str(uuid.uuid4()),
                "file_ids": [self.upload_bill()],
                "config": {"output_mode": "both_in_place"},
            },
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("combined verified write contract", response.text)

    def test_mock_policy_rejects_excel_both_and_preference_override(self):
        from minkops_platform.resources import REPOSITORY_ROOT
        from minkops_platform.solution_policy import bind_definition
        from minkops_platform.workflows import load_definition
        from psycopg.types.json import Jsonb

        definition = bind_definition(
            load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry"),
            "mock-client",
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute(
                """UPDATE workflows SET config_schema=%s,
                config_values=jsonb_set(config_values,'{output_mode}','"tally_in_place"')
                WHERE key='bill-entry' AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant') RETURNING id,config_values""",
                (Jsonb(definition.tenant_schema),),
            ).fetchone()
        bill = self.upload_bill()
        for mode in ("excel_in_place", "both_in_place", "draft_excel"):
            with self.subTest(mode=mode):
                response = self.client.post(
                    self.base + "/runs",
                    headers=self.csrf,
                    json={
                        "key": "bill-entry",
                        "request_key": str(uuid.uuid4()),
                        "file_ids": [bill],
                        "config": {"output_mode": mode},
                    },
                )
                self.assertEqual(response.status_code, 422, response.text)
                response = self.client.patch(
                    f"/api/tenants/mock-tenant/workflows/{row['id']}",
                    headers=self.csrf,
                    json={"config_values": {**row["config_values"], "output_mode": mode}},
                )
                self.assertEqual(response.status_code, 422, response.text)

    def test_missing_vendor_holds_then_resumes_with_confirmed_new_master(self):
        discovery = self.tally_discovery("same-company")
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        proposal = self.tally_result(run, bill)
        proposal["records"][0]["data"]["vendor"] = "New supplier"
        proposal["records"][0]["master_refs"]["vendor"] = {"ref": None, "evidence": "No discovered supplier matches the bill identifiers.", "new_supplier": True}
        self.process(run, proposal)
        result = self.client.get(self.base + f"/runs/{run['id']}").json()["result"]
        self.assertEqual(result["records"][0]["decision"], "hold")
        self.assertIn("New supplier", result["unresolved"][0]["reason"])
        reviewed = self.approve(run, result)
        self.assertEqual(reviewed["tally_writes"], [])
        new_discovery = self.tally_discovery(
            "same-company", extra_ledgers=["New supplier"], reuse_device=True
        )
        response = self.client.post(
            self.base + f"/runs/{run['id']}/resolve-bill",
            headers=self.csrf,
            json={
                "file_id": bill,
                "user_input": "",
                "reject": False,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["config"]["tally_target"]["discovery_id"], new_discovery)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            child = c.execute(
                "SELECT config FROM account_runs WHERE parent_run_id=%s", (run["id"],)
            ).fetchone()
            c.execute(
                "UPDATE account_runs SET config=config || '{\"batch_finished_count\":0}'::jsonb WHERE id=%s",
                (run["id"],),
            )
        self.assertEqual(child["config"]["tally_target"]["discovery_id"], new_discovery)
        from minkops_platform.accounts.batch import reconcile_once

        reconcile_once(URL)
        resumed = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(resumed["state"], "executing")

    def test_supplier_resume_cannot_change_tally_company_identity(self):
        discovery = self.tally_discovery("first-company")
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        self.process(
            run,
            {
                "records": [],
                "exceptions": [],
                "unresolved": [{"source_file_id": bill, "code": "supplier_missing", "reason": "Supplier missing"}],
            },
        )
        self.tally_discovery("replacement-company", reuse_device=True)
        response = self.client.post(
            self.base + f"/runs/{run['id']}/resolve-bill",
            headers=self.csrf,
            json={"file_id": bill, "user_input": "", "reject": False},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("scope changed", response.text)

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
                    "exceptions": [],
                }
            ],
            "exceptions": [],
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

    def tally_discovery(
        self,
        company_guid=None,
        *,
        extra_ledgers=(),
        reuse_device=False,
        multiple=False,
        books_from=None,
        voucher_types=("Purchase",),
        vouchers=(),
    ):
        self.native = "/api/tenants/mock-tenant/desktop"
        if not reuse_device:
            self.device = self.client.post(
                self.native + "/devices",
                headers=self.csrf,
                json={"name": "Bill PC", "installation_id": str(uuid.uuid4())},
            ).json()
        self.worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.7.0"}
        discovery = "/api/tenants/mock-tenant/discovery"
        categories = ["company", "ledgers", "voucher_types"]
        period = {"from": "2026-10-01", "to": "2026-10-31"}
        launched = self.client.post(
            discovery + "/runs",
            headers=self.csrf,
            json={
                "device_id": self.device["id"],
                "request_key": str(uuid.uuid4()),
                "config": {
                    "depth": "client_context",
                    "excel_source_ids": [],
                    "tally": {"port": 9000, "period": period},
                },
            },
        )
        self.assertEqual(launched.status_code, 202, launched.text)
        claim = self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        names = {
            "company": ["Test"],
            "ledgers": ["Supplier", "Purchases", "Tax", *extra_ledgers],
            "voucher_types": list(voucher_types),
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
                                "records": [v if isinstance(v, dict) else {"NAME": v} for v in names[k]],
                            }
                            for k in categories
                        ],
                    },
                }
            ]
        }
        if company_guid:
            receipt["sources"][0]["snapshot"]["collections"][0]["records"][0]["GUID"] = company_guid
        original = receipt["sources"][0]["snapshot"]
        guid = company_guid or self.device["id"] + "-company"
        identity = {"NAME": "Test", "GUID": guid, "COMPANYNUMBER": "100000",
                    **({"BOOKSFROM": books_from} if books_from else {})}
        company = {
            "company": "Test",
            "company_guid": guid,
            "identity": identity,
            "port": 9000,
            "status": "ready",
            "masters": {"status": "ready", "count": 0, "records": []},
            "vouchers": {"status": "ready", "count": len(vouchers), "records": [
                {"type": "VOUCHER", "data": {"GUID": f"v{i}", "DATE": "20261001", "VOUCHERTYPENAME": kind}}
                for i, kind in enumerate(vouchers)]},
        }
        for collection in original["collections"]:
            if collection["category"] == "company":
                continue
            kind = "LEDGER" if collection["category"] == "ledgers" else "VOUCHERTYPE"
            company["masters"]["records"].extend(
                {"type": kind, "data": r} for r in collection["records"]
            )
        company["masters"]["count"] = len(company["masters"]["records"])
        period = {"from": "2026-10-01", "to": "2026-10-31"}
        receipt["sources"][0]["snapshot"] = {
            "format_version": "2",
            "period": period,
            "companies": [company],
            "partial": False,
        }
        if multiple:
            other = copy.deepcopy(company)
            other.update(
                company="Beta",
                company_guid="beta-guid",
                identity={"NAME": "Beta", "GUID": "beta-guid", "COMPANYNUMBER": "100001"},
            )
            receipt["sources"][0]["snapshot"]["companies"].append(other)
        snapshot = receipt["sources"][0]["snapshot"]
        snapshot["company_scope"] = [
            {
                "company": c["company"],
                "company_guid": c["company_guid"],
                "company_number": c["identity"]["COMPANYNUMBER"],
            }
            for c in snapshot["companies"]
        ]
        r = self.client.post(
            f"/api/desktop/worker/jobs/{claim['id']}/finish",
            headers=self.worker,
            json={"claim_token": claim["claim_token"], "result": receipt},
        )
        self.assertEqual(r.status_code, 200, r.text)
        from minkops_platform.accounts.worker import process

        with psycopg.connect(URL, row_factory=dict_row) as c:
            mapping = c.execute(
                "SELECT mapping_run_id FROM discovery_runs WHERE id=%s",
                (launched.json()["id"],),
            ).fetchone()["mapping_run_id"]
            if mapping is not None:
                process(
                    c,
                    c.execute("SELECT * FROM account_runs WHERE id=%s", (mapping,)).fetchone(),
                    executor=lambda *args, **kwargs: {"sheets": [], "context_notes": []},
                )
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
                    "company_guid": run["config"]["tally_target"]
                    .get("companies", [{}])[0]
                    .get("references", {})
                    .get("company_guid"),
                    "company_evidence": "Buyer identity matches Test.",
                    "master_refs": {
                        field: {"ref": next(ref for ref, master in run["config"]["tally_target"]["companies"][0]["ledger_refs"].items()
                                            if master["name"] == data[field]),
                                "evidence": "Bill identifiers and discovered native definition match."}
                        for field in ("vendor", "purchase_ledger", "tax_ledger")
                    },
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
                    "exceptions": [],
                }
            ],
            "exceptions": [],
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
            route + "/plan?claim_token=" + claim["claim_token"], headers={**self.worker,"X-Minkops-Plan-Version":"3"}
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
        self.assertEqual(run["state"], "writing", run["result"])
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
        denied = self.client.post(
            self.base + f"/runs/{held['id']}/approve",
            headers=self.csrf,
            json={"result": edited, "acknowledge_findings": True},
        )
        self.assertEqual(denied.status_code, 422)
        response = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{held['id']}/{bill}",
            headers=self.csrf,
            json={"action": "guess"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        _, _, correction = self.tally_job(response.json())
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
            "exceptions": [],
        }
        result = {"records": [record], "exceptions": []}
        self.process(run, result)
        done = self.approve(run, result)
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["writes"], [])
        self.assertEqual(done["result"]["records"][0]["status"], "duplicate")
        self.assertFalse(any("Exact duplicate" in f for f in done["result"]["records"][0]["findings"]))
        self.assertIn("Exact duplicate", done["result"]["records"][0]["notes"][0])
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=cat)
        result["records"][0]["data"]["Amount"] = 24
        self.process(run, result)
        held = self.approve(run, result)
        self.assertEqual(held["state"], "review")
        edited = held["result"]
        edited["records"][0]["operation"] = "update"
        response = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{held['id']}/{bill}",
            headers=self.csrf,
            json={"action": "guess"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "writing")

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

    def test_same_vendor_invoice_can_route_to_two_companies_and_saves_are_grouped(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery("alpha-guid", multiple=True)
        inputs = [self.upload_bill(f"company-{i}.pdf") for i in range(3)]
        root, _ = self.launch(
            "bill-entry",
            file_ids=inputs,
            catalog_id=None,
            config={"output_mode": "tally_in_place", "discovery_id": did},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s ORDER BY file_ids->>0",
                (root["id"],),
            ).fetchall()
        for child, guid in zip(children, ("beta-guid", "alpha-guid", "beta-guid"), strict=True):
            result = self.tally_result(root, child["file_ids"][0])
            result["records"][0].update(
                company_guid=guid, company_evidence="Buyer registration matches " + guid
            )
            selected = next(c for c in root["config"]["tally_target"]["companies"] if c["references"]["company_guid"] == guid)
            for field, selection in result["records"][0]["master_refs"].items():
                selection["ref"] = next(ref for ref, master in selected["ledger_refs"].items()
                                        if master["name"] == result["records"][0]["data"][field])
            self.process(child, result)
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        approved = self.approve(loaded, loaded["result"])
        self.assertEqual(len(approved["tally_writes"]), 2)
        observed = []
        for _ in range(2):
            claim = self.client.post(
                "/api/desktop/worker/claim", headers=self.worker, json={}
            ).json()
            route = f"/api/desktop/worker/jobs/{claim['id']}"
            plan = self.client.get(
                route + f"/plan?claim_token={claim['claim_token']}", headers={**self.worker, "X-Minkops-Plan-Version": "3"}
            ).json()
            observed.append(plan["company"])
            reply = self.client.post(
                route + "/finish",
                headers=self.worker,
                json={
                    "claim_token": claim["claim_token"],
                    "result": {"outcome": "saved", "current": self.current(plan)},
                },
            )
            self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(observed, ["Beta", "Test"])
        done = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(
            sorted(r["status"] for r in done["result"]["records"]), ["duplicate", "saved", "saved"]
        )
        repeated = next(r for r in done["result"]["records"] if r["status"] == "duplicate")
        self.assertEqual((repeated["findings"], repeated["notes"]), ([], ["Repeated bill in this batch was skipped."]))

    def test_tally_discovery_plan_is_never_given_to_an_older_companion(self):
        self.native = "/api/tenants/mock-tenant/desktop"
        self.device = self.client.post(self.native + "/devices", headers=self.csrf, json={
            "name": "Old PC", "installation_id": str(uuid.uuid4())}).json()
        worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.7.0"}
        launched = self.client.post("/api/tenants/mock-tenant/discovery/runs", headers=self.csrf, json={
            "device_id": self.device["id"], "request_key": str(uuid.uuid4()),
            "config": {"depth": "client_context", "excel_source_ids": [],
                       "tally": {"port": 9000, "period": {"from": "2026-10-01", "to": "2026-10-31"}}}})
        self.assertEqual(launched.status_code, 202, launched.text)
        claim = self.client.post("/api/desktop/worker/claim", headers=worker, json={}).json()
        route = f"/api/desktop/worker/jobs/{claim['id']}/plan?claim_token={claim['claim_token']}"
        old = self.client.get(route, headers={**worker, "X-Minkops-Plan-Version": "2"})
        self.assertEqual(old.status_code, 409, old.text)
        self.assertIn("Update Minkops", old.json()["detail"])
        current = self.client.get(route, headers={**worker, "X-Minkops-Plan-Version": "3"})
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["sources"][0]["label"], "Companies open in Tally")

    def test_purchase_voucher_type_comes_from_discovery_not_a_fixed_name(self):
        """A practice that books purchases only under its own type can enter bills."""
        did = self.tally_discovery(voucher_types=(
            {"NAME": "Purchase GST", "PARENT": "Purchase", "GUID": "vt-gst"},
            {"NAME": "Purchase Order", "@_RESERVEDNAME": "Purchase Order", "GUID": "vt-po"},
            {"NAME": "Purchase Old", "PARENT": "Purchase", "GUID": "vt-old", "ISACTIVE": "No"},
        ))
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None, config={
            "output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions"})
        self.process(run, self.tally_result(run, bill))
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        claim, route, plan = self.tally_job(loaded)
        self.assertEqual(plan["format_version"], 3)
        self.assertEqual(plan["references"]["voucher_type"],
                         {"NAME": "Purchase GST", "GUID": "vt-gst", "PARENT": "Purchase", "ALTERID": None})
        receipt = {**self.current(plan), "voucher_type": "Purchase GST"}
        malformed = self.client.post(route + "/finish", headers=self.worker, json={
            "claim_token": claim["claim_token"], "result": {"outcome": "saved", "current": {**receipt, "voucher_type": ["x"]}}})
        self.assertEqual(malformed.status_code, 422, malformed.text)
        accepted = self.client.post(route + "/finish", headers=self.worker, json={
            "claim_token": claim["claim_token"], "result": {"outcome": "saved", "current": receipt}})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        saved = self.client.get(self.base + f"/runs/{run['id']}").json()["result"]["records"][0]
        self.assertEqual((saved["status"], saved["current"]["voucher_type"]), ("saved", "Purchase GST"))

    def test_several_purchase_types_need_an_explicit_choice_that_is_pinned(self):
        did = self.tally_discovery(
            "alpha-guid",
            voucher_types=({"NAME": "Purchase", "GUID": "vt-p"},
                           {"NAME": "Purchase GST", "PARENT": "Purchase", "GUID": "vt-gst"}),
            vouchers=("Purchase GST", "Purchase GST", "Purchase", "Journal"),
        )
        latest = self.client.get(f"/api/tenants/mock-tenant/discovery/latest?device_id={self.device['id']}").json()
        offered = latest["catalog"]["sources"][0]["snapshot"]["companies"][0]["purchase_voucher_types"]
        self.assertEqual(offered, {"default": "vt-gst", "candidates": [
            {"name": "Purchase", "guid": "vt-p", "used": 1}, {"name": "Purchase GST", "guid": "vt-gst", "used": 2}]})
        bill = self.upload_bill()
        config = {"output_mode": "tally_in_place", "discovery_id": did, "review_mode": "only_exceptions",
                  "company_mode": "locked", "locked_company_guid": "alpha-guid"}
        body = {"key": "bill-entry", "request_key": str(uuid.uuid4()), "file_ids": [bill], "catalog_id": None}
        missing = self.client.post(self.base + "/runs", headers=self.csrf, json={**body, "config": config})
        self.assertEqual(missing.status_code, 422, missing.text)
        self.assertIn("Choose the purchase voucher type for Test", missing.json()["detail"])
        stale = self.client.post(self.base + "/runs", headers=self.csrf, json={
            **body, "request_key": str(uuid.uuid4()),
            "config": {**config, "purchase_voucher_types": {"alpha-guid": "vt-unknown"}}})
        self.assertEqual(stale.status_code, 422, stale.text)
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None, config={
            **config, "purchase_voucher_types": {"alpha-guid": "vt-p"}})
        self.process(run, self.tally_result(run, bill))
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        _, _, plan = self.tally_job(loaded)
        self.assertEqual(plan["references"]["voucher_type"]["GUID"], "vt-p")

    def test_a_company_without_an_active_purchase_type_cannot_start_a_locked_run(self):
        did = self.tally_discovery("alpha-guid", voucher_types=(
            {"NAME": "Purchase", "GUID": "vt-p", "ISACTIVE": "No"},))
        bill = self.upload_bill()
        response = self.client.post(self.base + "/runs", headers=self.csrf, json={
            "key": "bill-entry", "request_key": str(uuid.uuid4()), "file_ids": [bill], "catalog_id": None,
            "config": {"output_mode": "tally_in_place", "discovery_id": did,
                       "company_mode": "locked", "locked_company_guid": "alpha-guid"}})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("no active purchase voucher type", response.json()["detail"])

    def test_locked_company_conflict_cannot_be_approved_into_a_write(self):
        did = self.tally_discovery("alpha-guid", multiple=True)
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={
                "output_mode": "tally_in_place",
                "discovery_id": did,
                "company_mode": "locked",
                "locked_company_guid": "alpha-guid",
            },
        )
        result = self.tally_result(run, bill)
        result["records"][0]["company_guid"] = "beta-guid"
        self.process(run, result)
        held = self.approve(run, result)
        self.assertEqual(held["result"]["records"][0]["status"], "held")
        self.assertEqual(held["tally_writes"], [])

    def test_conflicting_batch_requires_explicit_single_version_decision(self):
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
        self.assertEqual(approved["tally_writes"], [])
        selected = approved["result"]["records"][0]["source_file_id"]
        response = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{root['id']}/{selected}",
            headers=self.csrf, json={"action":"guess"})
        self.assertEqual(response.status_code,200,response.text)
        approved = response.json()
        self.assertEqual(len(approved["tally_writes"]), 1)
        self.assertEqual(
            [r["status"] for r in approved["result"]["records"]], ["writing", "held", "held"]
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
            [r["status"] for r in loaded["result"]["records"]], ["saved", "held", "held"]
        )
        self.assertEqual(loaded["state"], "review")

    def test_cancellation_late_tally_receipt_and_lease_expiry_do_not_replay_or_claim_success(self):
        self.verify_cancelled_tally_receipt()

    def test_stop_preserves_late_tally_receipt_and_prevents_new_save_plans(self):
        self.verify_cancelled_tally_receipt(control=True)

    def verify_cancelled_tally_receipt(self, control=False):
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
        cancelled = self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control", headers=self.csrf, json={"action": "stop"}) if control else self.client.post(
            self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(
            self.client.get(
                route + "/plan?claim_token=" + claim["claim_token"], headers={**self.worker, "X-Minkops-Plan-Version": "3"}
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
        self.assertEqual(final["state"], "stopped" if control else "failed")
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
                    "exceptions": [],
                    "unresolved": [{"source_file_id": bad, "code": "source_unreadable", "reason": "Unreadable invoice number"}],
                }
            )
            self.process(child, proposal)
        reconcile_once(URL)
        ready = self.client.get(self.base + f"/runs/{root['id']}").json()
        approved = self.approve(ready, ready["result"])
        claim, route, plan = self.tally_job(approved)
        receipt = self.client.post(
            route + "/finish",
            headers=self.worker,
            json={
                "claim_token": claim["claim_token"],
                "result": {"outcome": "saved", "current": self.current(plan)},
            },
        )
        self.assertEqual(receipt.status_code, 200, receipt.text)
        resumed = self.client.post(
            self.base + f"/runs/{root['id']}/resolve-bill",
            headers=self.csrf,
            json={"file_id": bad},
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            retry = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s AND state='queued'",
                (root["id"],),
            ).fetchall()
        self.assertEqual(len(retry), 1)
        self.assertEqual(retry[0]["file_ids"], [bad])
        self.assertNotIn("user_input", retry[0]["config"])
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
            summary = c.execute(
                "SELECT summary FROM tasks WHERE id=%s", (root["task_id"],)
            ).fetchone()["summary"]
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
        self.approve(second, self.excel_result(bill, 13))
        corrected = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{second['id']}/{bill}",
            headers=self.csrf,
            json={"action": "guess"},
        )
        self.assertEqual(corrected.status_code, 200, corrected.text)
        updated = corrected.json()
        write = updated["writes"][0]
        route = self.base + f"/runs/{second['id']}/writes/{write['id']}"
        saved = self.client.get(route + "/content").content
        response = self.client.post(
            route + "/verify", headers=self.csrf, files={"file": ("records.xlsx", saved)}
        )
        self.assertEqual(response.status_code, 200, response.text)
        corrected = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{first['id']}/{bill}",
            headers=self.csrf,
            json={"action": "guess"},
        )
        self.assertEqual(corrected.status_code, 200, corrected.text)
        held = corrected.json()
        self.assertEqual(held["state"], "review")
        self.assertEqual(held["writes"], [])
        self.assertEqual(held["result"]["records"][0]["current_excel"]["Amount"], 13)
        resumed = self.client.post(
            f"/api/tenants/mock-tenant/attention/bills/{held['id']}/{bill}",
            headers=self.csrf,
            json={"action": "guess"},
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], "writing")

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
            json={"file_id": ids[1]},
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
