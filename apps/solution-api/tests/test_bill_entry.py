"""MIN-117/118/119 integration against PostgreSQL and authenticated transport."""

import copy
import unittest
import uuid

import psycopg
import test_accounts_api as accounts_tests
from psycopg.rows import dict_row

URL = accounts_tests.URL


def confirm_patterns(discovery_id):
    """Seed each company's confirmed posting pattern from its own discovered masters."""
    from psycopg.types.json import Jsonb

    from minkops_platform.accounts.posting_profiles import validate
    from minkops_platform.accounts.vouchers import Masters

    with psycopg.connect(URL, row_factory=dict_row) as c:
        row = c.execute("SELECT tenant_id,catalog FROM discovery_runs WHERE id=%s", (discovery_id,)).fetchone()
        for company in row["catalog"]["sources"][0]["snapshot"]["companies"]:
            masters = Masters(company)
            types = [g for (kind, g), found in masters.by_key.items() if kind == "VOUCHERTYPE"
                     and masters.family(found[0]) == "purchase" and masters.scalar(found[0], "ISACTIVE").casefold() != "no"]
            if not types:
                continue
            payload = validate({"company_guid": company["company_guid"],
                                "families": {"invoice": {"family": "purchase", "voucher_type_guid": types[0]}, "credit_note": None},
                                "invoice_number": {"fields": ["REFERENCE"]}, "round_off": None, "tds": None,
                                "party_groups": ["Sundry Creditors"], "practice": [], "summary": ["Fixture pattern"]},
                               masters, company["company_guid"])
            # Each fixture discovery replaces any pattern an earlier test confirmed.
            c.execute("""UPDATE client_profiles SET status='superseded' WHERE tenant_id=%s AND kind='posting_profile'
                AND scope_key=%s AND status IN ('deriving','proposed','active')""", (row["tenant_id"], company["company_guid"]))
            c.execute("""INSERT INTO client_profiles(tenant_id,kind,scope_key,version,status,payload,provenance)
                SELECT %s,'posting_profile',%s,coalesce(max(version),0)+1,'active',%s,%s FROM client_profiles
                WHERE tenant_id=%s AND kind='posting_profile' AND scope_key=%s""",
                      (row["tenant_id"], company["company_guid"], Jsonb(payload), Jsonb({"discovery_id": str(discovery_id)}),
                       row["tenant_id"], company["company_guid"]))


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class BillEntryTests(unittest.TestCase):
    setUp = accounts_tests.AccountsTests.setUp
    launch = accounts_tests.AccountsTests.launch
    execute_discovery = accounts_tests.AccountsTests.execute_discovery

    def test_native_identities_name_the_entry_whatever_the_bill_prints(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "discovery_id": did, "review_mode": "only_exceptions"})
        proposal = self.tally_result(run, bill)
        proposal["records"][0]["document"]["supplier_name"] = "sup plier"
        self.process(run, proposal)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"], "writing", loaded.get("result"))
        self.assertEqual(loaded["result"]["records"][0]["data"]["vendor"], "Supplier")
        self.assertEqual([line["ledger"] for line in loaded["result"]["records"][0]["preview"]["lines"]],
                         ["Supplier", "Purchases", "Tax"])
        _, _, plan = self.tally_job(loaded)
        self.assertEqual(plan["header"]["party_ledger"], "Supplier")
        self.assertEqual(sorted(plan["references"]["ledgers"]), ["Purchases", "Supplier", "Tax"])

    def test_exception_only_batch_does_not_require_approval_for_clean_sibling(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery()
        inputs = [self.upload_bill("clean.pdf"), self.upload_bill("uncertain.pdf")]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "discovery_id": did, "review_mode": "only_exceptions"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)).fetchall()
        for child in children:
            proposal = self.tally_result(root, child["file_ids"][0])
            if child["file_ids"][0] == inputs[1]:
                proposal["records"][0]["voucher"]["party"]["ledger_guid"] = "foreign-catalog"
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
        run, _ = self.launch("bill-entry", file_ids=[bill], config={"discovery_id": did})
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
            "discovery_id": did, "review_mode": "all_outputs"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = {c_["file_ids"][0]: c_ for c_ in c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],))}
        # Two bills are read; the third is still waiting when the operator stops.
        self.process(children[inputs[0]], self.tally_result(root, inputs[0]))
        held = self.tally_result(root, inputs[1])
        held["records"][0]["voucher"]["party"]["ledger_guid"] = "foreign-catalog"
        self.process(children[inputs[1]], held)
        stop = self.client.post(f"/api/tenants/mock-tenant/tasks/{root['task_id']}/control",
                                headers=self.csrf, json={"action": "stop"})
        self.assertEqual(stop.status_code, 200, stop.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            keys = [r["event_key"] for r in c.execute(
                "SELECT event_key FROM attention_items WHERE task_id=%s ORDER BY event_key", (root["task_id"],))]
        self.assertEqual(keys, sorted(f"bill:{root['id']}:{f}:bill" for f in inputs[:2]))

    def test_stopping_before_bill_validation_retains_input_without_trusting_raw_values(self):
        from psycopg.types.json import Jsonb

        did = self.tally_discovery()
        bill = self.upload_bill("raw-stop.pdf")
        root, _ = self.launch("bill-entry", file_ids=[bill, self.upload_bill("unread-stop.pdf")], config={
            "discovery_id": did, "review_mode": "all_outputs"})
        # Provider output is persisted before normalization. A concurrent Stop
        # must preserve the input even though no trusted display data exists yet.
        raw = self.tally_result(root, bill)
        self.assertNotIn("data", raw["records"][0])
        with psycopg.connect(URL) as c:
            c.execute("UPDATE account_runs SET state='executing',result=%s WHERE parent_run_id=%s AND file_ids=%s",
                      (Jsonb(raw), root["id"], Jsonb([bill])))
        response = self.client.post(f"/api/tenants/mock-tenant/tasks/{root['task_id']}/control",
                                    headers=self.csrf, json={"action": "stop"})
        self.assertEqual(response.status_code, 200, response.text)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["state"], "stopped")
        self.assertFalse(loaded["tally_writes"])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            items = c.execute("SELECT target FROM attention_items WHERE task_id=%s", (root["task_id"],)).fetchall()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["target"]["file_id"], bill)
        self.assertIsNone(items[0]["target"]["vendor"])

    def exception_only_batch(self, count=2):
        did = self.tally_discovery()
        inputs = [self.upload_bill(f"bill-{i}.pdf") for i in range(count)]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "discovery_id": did, "review_mode": "only_exceptions"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s", (root["id"],)).fetchall()
        return root, inputs, children

    def numbered_result(self, run, bill, invoice):
        result = self.tally_result(run, bill)
        result["records"][0]["document"]["number"] = invoice
        for evidence in result["records"][0]["evidence"]:
            if evidence["field"] == "number":
                evidence["quote"] = invoice
        return result

    def test_batch_aggregation_never_decodes_child_execution_contexts(self):
        import json

        from psycopg.types.json import set_json_loads

        from minkops_platform.accounts.batch import _reconcile

        root, inputs, children = self.exception_only_batch()
        for child in children:
            self.process(child, self.numbered_result(root, child['file_ids'][0], str(child['id'])))
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute("UPDATE account_runs SET config=config || '{\"aggregation_context_marker\":true}'::jsonb WHERE parent_run_id=%s", (root['id'],))
            parent = c.execute('SELECT * FROM account_runs WHERE id=%s', (root['id'],)).fetchone()

            def load_outcome(value):
                if b'aggregation_context_marker' in bytes(value):
                    raise AssertionError('Aggregation must not deserialize immutable child execution catalogs.')
                return json.loads(value)

            set_json_loads(load_outcome, c)
            _reconcile(c, parent)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(len(loaded['result']['records']), len(inputs))

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
            self.assertEqual(record["allowed_actions"], ["retry_save", "nothing"])

    def test_native_save_refusal_replaces_cached_decisions_with_retry_save(self):
        from unittest.mock import patch

        did = self.tally_discovery()
        bill = self.upload_bill("native-refusal.pdf")
        run, _ = self.launch("bill-entry", file_ids=[bill], config={"discovery_id": did})
        proposal = self.tally_result(run, bill)
        self.process(run, proposal)
        approved = self.approve(run, proposal)
        self.save_receipt(approved, "MOCK-1", "Tally is busy")
        with patch("minkops_platform.runtime.assets.hydrate", side_effect=AssertionError("Status loaded execution evidence")):
            response = self.client.get(self.base + f"/runs/{run['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        held = response.json()
        self.assertEqual(held["state"], "review")
        self.assertEqual(held["result"]["records"][0]["allowed_actions"], ["retry_save", "nothing"])

    def test_retry_save_after_reconnecting_an_unavailable_pc(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "discovery_id": did, "review_mode": "only_exceptions"})
        self.client.delete(f"{self.native}/devices/{self.device['id']}", headers=self.csrf)
        self.process(run, self.tally_result(run, bill))
        held = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual((held["state"], held["result"]["records"][0]["status"]), ("review", "held"))
        offline = self.client.post(f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}",
                                   headers=self.csrf, json={"action": "retry_save"})
        self.assertEqual(offline.status_code, 409, offline.text)
        self.device = self.client.post(self.native + "/devices", headers=self.csrf, json={
            "name": "Bill PC", "installation_id": self.device["installation_id"]}).json()
        self.worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.9.0"}
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
        current = self.current(plan)
        self.assertEqual(current["reference"], invoice)
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
            "discovery_id": did})
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
        self.assertEqual(loaded["result"]["deferred"], [{"source_file_id": inputs[0], "code": "extraction_failed", "reason": "Unreadable"}])

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
            "discovery_id": did, "review_mode": "only_exceptions"})
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
            "discovery_id": did, "review_mode": "only_exceptions"})
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

    def split_result(self, run, bill, split=True):
        """Central and state tax as their own lines, or one IGST line, for the same bill."""
        result = self.tally_result(run, bill)
        lines = result["records"][0]["voucher"]["lines"]
        if split:
            lines[1:] = [{**lines[1], "ledger_guid": f"{name}-guid", "amount": 9, "evidence": f"{head.upper()} 9%",
                          "tax": {"head": head, "rate": 9, "taxable": 100}} for name, head in (("Tax", "cgst"), ("SGST", "sgst"))]
        return result

    def test_split_tax_native_plan_and_receipt_cannot_collapse_components(self):
        did = self.tally_discovery(extra_ledgers=("SGST",))
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={"discovery_id": did,
                                                                    "review_mode": "only_exceptions"})
        self.process(run, self.split_result(run, bill))
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"], "writing", loaded.get("result"))
        claim, route, plan = self.tally_job(loaded)
        for version in ("3", "4"):
            older = self.client.get(route + '/plan?claim_token=' + claim["claim_token"], headers={**self.worker, "X-Minkops-Plan-Version": version})
            self.assertEqual(older.status_code, 409, older.text)
            self.assertIn("Update Minkops", older.json()["detail"])
        self.assertEqual((plan["format_version"], plan["voucher_type"]["NAME"]), (5, "Purchase"))
        self.assertEqual(sorted((ln["ledger"], ln["amount_cents"]) for ln in plan["lines"] if ln["ledger"] in ("Tax", "SGST")),
                         [("SGST", 900), ("Tax", 900)])
        collapsed = self.current(plan, lines=[{"ledger": "Purchases", "amount_cents": -10000}, {"ledger": "Supplier", "amount_cents": 11800},
                                              {"ledger": "Tax", "amount_cents": -1800}])
        rejected = self.client.post(route + '/finish', headers=self.worker, json={"claim_token": claim["claim_token"],
                                                                                 "result": {"outcome": "saved", "current": collapsed}})
        self.assertGreaterEqual(rejected.status_code, 400, rejected.text)
        accepted = self.client.post(route + '/finish', headers=self.worker, json={"claim_token": claim["claim_token"],
                                                                                 "result": {"outcome": "saved", "current": self.current(plan)}})
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_conflicting_tax_treatments_of_one_bill_hold_both_before_dispatch(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery(extra_ledgers=("SGST",))
        bills = [self.upload_bill("one.pdf"), self.upload_bill("two.pdf")]
        root, _ = self.launch("bill-entry", file_ids=bills, config={"discovery_id": did,
                                                                    "review_mode": "only_exceptions"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s ORDER BY file_ids->>0", (root["id"],)).fetchall()
        for child, split in zip(children, (True, False), strict=True):
            self.process(child, self.split_result(root, child["file_ids"][0], split))
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["tally_writes"], [])
        self.assertTrue(all(r.get("status") == "held" for r in loaded["result"]["records"]))

    def test_child_wide_findings_hold_only_that_input(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery()
        inputs = [self.upload_bill("clean.pdf"), self.upload_bill("uncertain.pdf")]
        root, _ = self.launch("bill-entry", file_ids=inputs, config={
            "discovery_id": did, "review_mode": "only_exceptions"})
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
            config={"discovery_id": first},
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
            "config": {"discovery_id": first},
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

    def test_missing_vendor_holds_then_resumes_with_confirmed_new_master(self):
        discovery = self.tally_discovery("same-company")
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            config={"discovery_id": discovery},
        )
        proposal = self.tally_result(run, bill)
        proposal["records"][0]["document"]["supplier_name"] = "New supplier"
        proposal["records"][0]["voucher"]["party"] = {"ledger_guid": None, "evidence": "No discovered supplier matches the bill identifiers.", "new_supplier": True}
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
            f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}",
            headers=self.csrf,
            json={"action": "retry"},
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
            config={"discovery_id": discovery},
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
            f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}",
            headers=self.csrf,
            json={"action": "retry"},
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
        native_ids=True,
        siblings=False,
        voucher_padding=0,
        confirmed_patterns=True,
    ):
        """`native_ids` gives masters the GUID/PARENT/ALTERID a live export carries.

        `multiple` adds companies (True adds Beta); `siblings` makes them one
        business split by year (shared GSTIN, consecutive books); `voucher_padding`
        bulks each voucher to model a real period's history.
        """
        self.native = "/api/tenants/mock-tenant/desktop"
        if not reuse_device:
            self.device = self.client.post(
                self.native + "/devices",
                headers=self.csrf,
                json={"name": "Bill PC", "installation_id": str(uuid.uuid4())},
            ).json()
        self.worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.9.0"}
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
        if native_ids:
            for k, parent in (("ledgers", "Sundry Creditors"), ("voucher_types", None)):
                names[k] = [v if isinstance(v, dict) else {"NAME": v, "GUID": f"{v}-guid", "ALTERID": "4",
                                                           **({"PARENT": parent} if parent else {})} for v in names[k]]
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
                {"type": "VOUCHER", "data": {"GUID": f"v{i}", "DATE": "20261001", "VOUCHERTYPENAME": kind,
                                             **({"NARRATION": "x" * voucher_padding} if voucher_padding else {})}}
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
        if siblings:
            company["identity"].update(GSTIN="27AAACS1234A1Z5", BOOKSFROM="20250401")
        for number in range(int(multiple)):
            other = copy.deepcopy(company)
            name, guid = ("Beta", "beta-guid") if number == 0 else (f"Company {number}", f"company-{number}-guid")
            other.update(company=name, company_guid=guid,
                         identity={"NAME": name, "GUID": guid, "COMPANYNUMBER": str(100001 + number),
                                   **({"GSTIN": "27AAACS1234A1Z5", "BOOKSFROM": f"{2026 + number}0401"} if siblings else {})})
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
        if confirmed_patterns:
            confirm_patterns(launched.json()["id"])
        return launched.json()["id"]

    def tally_result(self, run, bill, total=118):
        """A bill-entry 0.14 voucher proposal: purchase line plus 18% IGST."""
        company = run["config"]["tally_target"].get("companies", [{}])[0]
        guid = company.get("references", {}).get("company_guid")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            pattern = c.execute("""SELECT payload FROM client_profiles WHERE kind='posting_profile' AND scope_key=%s
                AND status='active' ORDER BY version DESC LIMIT 1""", (guid,)).fetchone()
        voucher_type = pattern["payload"]["families"]["invoice"]["voucher_type_guid"] if pattern else "Purchase-guid"
        return {
            "records": [
                {
                    "source_file_id": bill,
                    "company_guid": guid,
                    "company_evidence": "Buyer identity matches Test.",
                    "operation": "append",
                    "document": {"kind": "invoice", "number": "MOCK-1", "date": "2026-10-01", "total": total,
                                 "supplier_name": "Supplier", "supplier_gstin": None, "origin": "domestic"},
                    "voucher": {
                        "family": "purchase",
                        "voucher_type_guid": voucher_type,
                        "party": {"ledger_guid": "Supplier-guid", "new_supplier": False,
                                  "evidence": "Bill identifiers and discovered native definition match."},
                        "lines": [
                            {"role": "expense", "ledger_guid": "Purchases-guid", "side": "debit", "amount": total - 18,
                             "cost_centre_guid": None, "cost_category_guid": None, "tax": None, "evidence": "Item total"},
                            {"role": "tax", "ledger_guid": "Tax-guid", "side": "debit", "amount": 18,
                             "cost_centre_guid": None, "cost_category_guid": None,
                             "tax": {"head": "igst", "rate": 18, "taxable": 100}, "evidence": "IGST 18%"},
                        ],
                    },
                    "evidence": [{"field": f, "page": 1, "quote": q} for f, q in
                                 (("number", "MOCK-1"), ("date", "01/10/2026"), ("total", str(total)), ("supplier", "Supplier"))],
                    "exceptions": [],
                }
            ],
            "exceptions": [],
        }

    def route_bills(self, root, routes, dates=None):
        """Answer each triage stage (file -> company GUID or None), then fan out."""
        from minkops_platform.accounts.batch import reconcile_once

        with psycopg.connect(URL, row_factory=dict_row) as c:
            stages = c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s AND config->>'stage'='triage' "
                               "AND NOT coalesce((config->>'expanded')::boolean,false)", (root["id"],)).fetchall()
        self.assertTrue(stages, "Many open companies route bills before posting.")
        for stage in stages:
            self.process(stage, {"bills": [{
                "source_file_id": f, "company_guid": routes[f],
                "company_evidence": "Buyer GSTIN matches." if routes[f] else "",
                "documents": [{"kind": "invoice", "number": "MOCK-1", "date": (dates or {}).get(f, "2026-10-01"),
                               "supplier_name": "Supplier", "supplier_gstin": None}],
                "exception": None if routes[f] else {"code": "company_unresolved", "detail": "Two companies fit."},
            } for f in stage["file_ids"]]})
        reconcile_once(URL)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            return {r["file_ids"][0]: r for r in c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s AND config->>'stage' IS NULL "
                "AND NOT coalesce((config->>'superseded')::boolean,false)", (root["id"],))}

    def tally_job(self, run, version="5"):
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
            route + "/plan?claim_token=" + claim["claim_token"], headers={**self.worker,"X-Minkops-Plan-Version":version}
        )
        self.assertEqual(plan.status_code, 200, plan.text)
        return claim, route, plan.json()

    def observed_v5(self, plan, **overrides):
        """The voucher a protocol-5 companion reports for exactly this plan."""
        lines = sorted(({"ledger": ln["ledger"], "amount_cents": ln["amount_cents"] if ln["side"] == "credit" else -ln["amount_cents"]}
                        for ln in plan["lines"]), key=lambda e: (e["ledger"], e["amount_cents"]))
        return {"guid": "a1b2c3d4-0000-4000-8000-000000000007", "master_id": "1", "date": plan["header"]["date"].replace("-", ""),
                "voucher_type": plan["voucher_type"]["NAME"], "family": plan["family"], "reference": plan["header"]["reference"],
                "number": "", "narration": plan["header"]["narration"], "party_ledger": plan["header"]["party_ledger"],
                "tag": None, "lines": lines, "allocations": [], "fingerprint": "v5:" + "b" * 64, **overrides}

    def current(self, plan, total=None, **overrides):
        """The v5 voucher a companion reports; `total` reports a different saved version."""
        current = self.observed_v5(plan, **overrides)
        if total is not None:
            current["lines"] = sorted([{"ledger": "Supplier", "amount_cents": total * 100},
                                       {"ledger": "Purchases", "amount_cents": -(total - 18) * 100},
                                       {"ledger": "Tax", "amount_cents": -1800}], key=lambda e: e["ledger"])
        return current

    def test_tally_confirmation_approval_scoped_dispatch_and_exact_receipt_replay(self):
        discovery_id = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"discovery_id": discovery_id},
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
        bad["result"]["current"]["lines"][0]["amount_cents"] += 1
        self.assertEqual(
            self.client.post(route + "/finish", headers=self.worker, json=bad).status_code, 422
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
            config={"discovery_id": discovery_id},
        )
        self.process(repeat, self.tally_result(repeat, bill))
        repeat = self.approve(repeat, self.tally_result(repeat, bill))
        _, _, replayed_plan = self.tally_job(repeat)
        self.assertEqual(replayed_plan["remote_id"], plan["remote_id"])

    def test_protocol_five_companion_saves_the_approved_bill_as_a_verified_v5_voucher(self):
        discovery_id = self.tally_discovery(native_ids=True)
        bill = self.upload_bill("native.pdf")
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None,
                             config={"discovery_id": discovery_id})
        self.process(run, self.tally_result(run, bill))
        run = self.approve(run, self.tally_result(run, bill))
        claim, route, plan = self.tally_job(run, version="5")
        self.assertEqual((plan["format_version"], plan["family"], plan["fence"]), (5, "purchase", "retry_after_read"))
        self.assertEqual(plan["duplicate"]["window"], {"from": "2026-04-01", "to": "2027-03-31"})
        self.assertEqual(sorted((ln["ledger"], ln["side"], ln["amount_cents"]) for ln in plan["lines"]),
                         [("Purchases", "debit", 10000), ("Supplier", "credit", 11800), ("Tax", "debit", 1800)])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            stored = c.execute("SELECT plan,identity FROM account_tally_writes WHERE run_id=%s", (run["id"],)).fetchone()
        self.assertEqual(stored["plan"], plan)  # New approvals store the native v5 plan itself.
        self.assertEqual(plan["identity"]["hash"], stored["identity"])
        bad = self.observed_v5(plan, lines=[{**e, "amount_cents": e["amount_cents"] + (1 if e["amount_cents"] > 0 else 0)} for e in self.observed_v5(plan)["lines"]])
        refused = self.client.post(route + "/finish", headers=self.worker,
                                   json={"claim_token": claim["claim_token"], "result": {"outcome": "saved", "current": bad}})
        self.assertGreaterEqual(refused.status_code, 400)
        receipt = {"claim_token": claim["claim_token"], "result": {"outcome": "saved", "current": self.observed_v5(plan)}}
        r = self.client.post(route + "/finish", headers=self.worker, json=receipt)
        self.assertEqual(r.status_code, 200, r.text)
        saved = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(saved["state"], "completed")
        current = saved["result"]["records"][0]["current"]
        self.assertEqual((current["invoice_number"], current["vendor"], current["fingerprint"][:3]), ("MOCK-1", "Supplier", "v5:"))
        self.assertIn({"ledger": "Supplier", "amount": 11800}, current["entries"])

    def test_correction_handoff_preserves_old_snapshot_and_requires_explicit_edit(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"discovery_id": did},
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
        self.assertEqual(correction["expected"]["fingerprint"], "v5:" + "b" * 64)

    def test_batch_failed_bill_does_not_discard_successful_sibling(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        good = self.upload_bill("good.pdf")
        bad = self.upload_bill("bad.pdf")
        root, _ = self.launch(
            "bill-entry",
            file_ids=[good, bad],
            catalog_id=None,
            config={"discovery_id": did},
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
            config={"discovery_id": did},
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
            config={"discovery_id": did},
        )
        routes = dict(zip(inputs, ("beta-guid", "alpha-guid", "beta-guid"), strict=True))
        children = self.route_bills(root, routes)
        for file_id, child in children.items():
            guid = routes[file_id]
            # Each posting session sees only its routed company's evidence.
            self.assertEqual(child["config"]["company_scope"], [guid])
            self.assertEqual([c["references"]["company_guid"] for c in child["config"]["tally_target"]["companies"]], [guid])
            result = self.tally_result(root, file_id)
            result["records"][0].update(company_guid=guid, company_evidence="Buyer registration matches " + guid)
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
                route + f"/plan?claim_token={claim['claim_token']}", headers={**self.worker, "X-Minkops-Plan-Version": "5"}
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
        worker = {"Authorization": "Bearer " + self.device["credential"], "X-Minkops-Companion-Version": "0.9.0"}
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

    def test_discovery_review_names_companies_added_or_no_longer_open(self):
        first = self.tally_discovery("alpha-guid")

        def detail(run):
            return self.client.get(f"/api/tenants/mock-tenant/discovery/runs/{run}").json()

        self.assertIsNone(detail(first)["scope_changes"], "a first discovery has nothing to compare")
        wider = self.tally_discovery("alpha-guid", multiple=True, reuse_device=True)
        self.assertEqual(detail(wider)["scope_changes"], {
            "added": [{"company": "Beta", "company_guid": "beta-guid"}], "removed": []})
        narrower = self.tally_discovery("alpha-guid", reuse_device=True)
        self.assertEqual(detail(narrower)["scope_changes"], {
            "added": [], "removed": [{"company": "Beta", "company_guid": "beta-guid"}]})
        self.assertEqual(detail(wider)["scope_changes"]["added"][0]["company"], "Beta",
                         "each run compares with the confirmation before it")

    def test_a_bill_moves_to_the_year_split_sibling_whose_books_cover_its_date(self):
        did = self.tally_discovery("alpha-guid", multiple=True, siblings=True)
        bills = [self.upload_bill("this-year.pdf"), self.upload_bill("last-year.pdf"), self.upload_bill("future.pdf")]
        root, _ = self.launch("bill-entry", file_ids=bills, catalog_id=None,
                              config={"discovery_id": did})
        companies = {c["references"]["company_guid"]: c for c in root["config"]["tally_target"]["companies"]}
        self.assertEqual((companies["alpha-guid"]["period_to"], companies["beta-guid"]["period_to"]), ("2026-03-31", None))
        # Triage names the older company for all three; the dates decide.
        children = self.route_bills(root, dict.fromkeys(bills, "alpha-guid"),
                                    {bills[0]: "2026-10-01", bills[1]: "2025-11-01", bills[2]: "2024-01-15"})
        self.assertEqual(children[bills[0]]["config"]["company_scope"], ["beta-guid"])
        self.assertIn("routed from Test", children[bills[0]]["config"]["triage"]["note"])
        self.assertEqual(children[bills[1]]["config"]["company_scope"], ["alpha-guid"])
        held = children[bills[2]]
        self.assertEqual((held["state"], held["result"]["unresolved"][0]["code"]), ("review", "date_outside_company_period"))

    def test_twenty_open_companies_launch_because_each_bill_gets_one_company(self):
        import json

        from minkops_platform.accounts.client_context import context_assets

        did = self.tally_discovery("alpha-guid", multiple=19, vouchers=("Purchase",) * 30, voucher_padding=16_000)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            catalog = c.execute("SELECT catalog FROM discovery_runs WHERE id=%s", (did,)).fetchone()["catalog"]
        everything = sum(len(a["content"]) for a in context_assets(catalog)[0])
        self.assertGreater(everything, 8_000_000, "Sending every company's discovery to a bill no longer fits.")
        bill = self.upload_bill("twenty.pdf")
        root, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None,
                              config={"discovery_id": did})
        children = self.route_bills(root, {bill: "company-7-guid"})
        child = children[bill]
        bound = [b for b in child["config"]["authorized_bindings"] if b["resource_id"].startswith("discovery-")]
        self.assertTrue(bound)
        sizes = json.dumps(child["config"]["authorized_bindings"])
        self.assertLess(len(sizes), 20_000)
        result = self.tally_result(root, bill)
        result["records"][0].update(company_guid="company-7-guid", company_evidence="Buyer GSTIN matches Company 7.")
        self.process(child, result)
        from minkops_platform.accounts.batch import reconcile_once
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{root['id']}").json()
        self.assertEqual(loaded["result"]["records"][0]["company_name"], "Company 7", loaded["result"])

    def test_purchase_voucher_type_comes_from_discovery_not_a_fixed_name(self):
        """A practice that books purchases only under its own type can enter bills."""
        did = self.tally_discovery(voucher_types=(
            {"NAME": "Purchase GST", "PARENT": "Purchase", "GUID": "vt-gst"},
            {"NAME": "Purchase Order", "@_RESERVEDNAME": "Purchase Order", "GUID": "vt-po"},
            {"NAME": "Purchase Old", "PARENT": "Purchase", "GUID": "vt-old", "ISACTIVE": "No"},
        ))
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None, config={
            "discovery_id": did, "review_mode": "only_exceptions"})
        self.process(run, self.tally_result(run, bill))
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        claim, route, plan = self.tally_job(loaded)
        self.assertEqual((plan["format_version"], plan["voucher_type"]), (5, {"NAME": "Purchase GST", "GUID": "vt-gst"}))
        receipt = self.current(plan)
        malformed = self.client.post(route + "/finish", headers=self.worker, json={
            "claim_token": claim["claim_token"], "result": {"outcome": "saved", "current": {**receipt, "voucher_type": ["x"]}}})
        self.assertEqual(malformed.status_code, 422, malformed.text)
        accepted = self.client.post(route + "/finish", headers=self.worker, json={
            "claim_token": claim["claim_token"], "result": {"outcome": "saved", "current": receipt}})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        saved = self.client.get(self.base + f"/runs/{run['id']}").json()["result"]["records"][0]
        self.assertEqual((saved["status"], saved["current"]["voucher_type"]), ("saved", "Purchase GST"))

    def test_several_purchase_types_follow_the_confirmed_pattern_without_a_launch_choice(self):
        did = self.tally_discovery(
            "alpha-guid",
            voucher_types=({"NAME": "Purchase", "GUID": "vt-p"},
                           {"NAME": "Purchase GST", "PARENT": "Purchase", "GUID": "vt-gst"}),
            vouchers=("Purchase GST", "Purchase GST", "Purchase", "Journal"),
        )
        latest = self.client.get(f"/api/tenants/mock-tenant/discovery/latest?device_id={self.device['id']}").json()
        self.assertNotIn("purchase_voucher_types", latest["catalog"]["sources"][0]["snapshot"]["companies"][0])
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None, config={
            "discovery_id": did, "review_mode": "only_exceptions",
            "company_mode": "locked", "locked_company_guid": "alpha-guid"})
        self.process(run, self.tally_result(run, bill))
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"], "writing", loaded["result"])
        _, _, plan = self.tally_job(loaded)
        self.assertEqual(plan["voucher_type"]["GUID"], "vt-p")  # The fixture's confirmed pattern.

    def test_a_company_without_an_active_purchase_type_waits_for_a_pattern(self):
        did = self.tally_discovery("inactive-guid", voucher_types=(
            {"NAME": "Purchase", "GUID": "vt-p", "ISACTIVE": "No"},))
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None, config={
            "discovery_id": did,
            "company_mode": "locked", "locked_company_guid": "inactive-guid"})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            config = c.execute("SELECT config FROM account_runs WHERE id=%s", (run["id"],)).fetchone()["config"]
        self.assertIn("awaits", config, "No pattern can name an inactive type; nothing posts until one is confirmed.")

    def test_locked_company_conflict_cannot_be_approved_into_a_write(self):
        did = self.tally_discovery("alpha-guid", multiple=True)
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={
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
            config={"discovery_id": did},
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

    def test_stop_keeps_late_tally_receipt_without_replay_or_claiming_success(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"discovery_id": did},
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
        stopped = self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control",
                                   headers=self.csrf, json={"action": "stop"})
        self.assertEqual(stopped.status_code, 200, stopped.text)
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
        self.assertEqual(final["state"], "stopped")
        self.assertIsNotNone(final["tally_writes"][0]["verified_at"])

    def test_human_clarification_retries_only_failed_bill_without_replaying_good_input(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        good, bad = self.upload_bill("good.pdf"), self.upload_bill("bad.pdf")
        root, _ = self.launch(
            "bill-entry",
            file_ids=[good, bad],
            catalog_id=None,
            config={"discovery_id": did},
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
            f"/api/tenants/mock-tenant/attention/bills/{root['id']}/{bad}",
            headers=self.csrf,
            json={"action": "retry"},
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            retry = c.execute(
                "SELECT * FROM account_runs WHERE parent_run_id=%s AND state='queued'",
                (root["id"],),
            ).fetchall()
        self.assertEqual(len(retry), 1)
        self.assertEqual(retry[0]["file_ids"], [bad])
        result = self.tally_result(root, bad)
        result["records"][0]["document"]["number"] = "MOCK-2"
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
        self.assertEqual(summary, "2 bill entries read; 1 ready to write; 0 bills need attention.")

    def test_pending_bill_reservation_holds_only_conflicting_intent(self):
        did = self.tally_discovery()
        bill = self.upload_bill()
        first, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"discovery_id": did},
        )
        self.process(first, self.tally_result(first, bill))
        self.approve(first, self.tally_result(first, bill))
        second, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"discovery_id": did},
        )
        self.process(second, self.tally_result(second, bill))
        held = self.approve(second, self.tally_result(second, bill))
        self.assertEqual(held["state"], "review")
        self.assertEqual(held["tally_writes"], [])
        self.assertEqual(held["result"]["records"][0]["status"], "held")

    def test_rejected_failed_input_does_not_reappear_when_another_bill_is_clarified(self):
        from minkops_platform.accounts.batch import reconcile_once

        did = self.tally_discovery()
        ids = [self.upload_bill(f"failed-{i}.pdf") for i in range(2)]
        root, _ = self.launch(
            "bill-entry",
            file_ids=ids,
            catalog_id=None,
            config={"discovery_id": did},
        )
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE account_runs SET state='failed',error='Unreadable' WHERE parent_run_id=%s",
                (root["id"],),
            )
        reconcile_once(URL)
        decide = f"/api/tenants/mock-tenant/attention/bills/{root['id']}/"
        rejected = self.client.post(decide + ids[0], headers=self.csrf, json={"action": "nothing"})
        self.assertEqual(rejected.status_code, 200, rejected.text)
        retry = self.client.post(decide + ids[1], headers=self.csrf, json={"action": "retry"})
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
            config={"discovery_id": did},
        )
        self.process(first, self.tally_result(first, bill))
        first = self.approve(first, self.tally_result(first, bill))
        did = self.tally_discovery(guid)
        second_device, second_worker = self.device, self.worker
        second, _ = self.launch(
            "bill-entry",
            file_ids=[bill],
            catalog_id=None,
            config={"discovery_id": did},
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
