"""Bulk consent is previewed, tenant/operator scoped, atomic and replay-safe."""
import unittest

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import test_bill_entry as fixtures

URL = fixtures.URL


@unittest.skipUnless(URL, "TEST_DATABASE_URL required")
class BulkBillTests(unittest.TestCase):
    for _method in ("setUp", "launch", "upload_bill", "process", "tally_discovery", "tally_result", "tally_job", "current"):
        locals()[_method] = getattr(fixtures.BillEntryTests, _method)

    def group(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery("bulk-company")
        files = [self.upload_bill(f"bulk-{i}.pdf") for i in range(4)]
        run, _ = self.launch("bill-entry", file_ids=files, config={"output_mode": "tally_in_place", "discovery_id": did})
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = {r["file_ids"][0]: r for r in c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s", (run["id"],))}
        for index, file in enumerate(files):
            result = self.tally_result(run, file)
            row = result["records"][0]
            supplier = "New Supplier" if index < 3 else "Different Supplier"
            row["document"].update(supplier_name=supplier, number=f"BULK-{index}", total=100)
            row["voucher"]["party"] = {"ledger_guid": None, "new_supplier": True, "evidence": "Printed supplier name; no discovered match."}
            row["voucher"]["lines"] = [{**row["voucher"]["lines"][0], "amount": 100}]
            for evidence in row["evidence"]:
                if evidence["field"] == "supplier": evidence["quote"] = supplier
                if evidence["field"] == "total": evidence["quote"] = "100"
            self.process(children[file], result)
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.trigger_index = next(i for i, r in enumerate(loaded["result"]["records"]) if r["source_file_id"] == files[0])
        return run, files, f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{files[0]}"

    def preview(self, route, action):
        response = self.client.post(route + "/bulk-preview", headers=self.csrf, json={"action": action, "proposal": self.trigger_index})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["count"], 3)
        return response.json()

    def test_three_similar_deferrals_leave_the_other_supplier_and_audit_each_actor_once(self):
        run, files, route = self.group()
        preview = self.preview(route, "nothing")
        self.assertIn("New Supplier", preview["description"])
        body = {"action": "nothing", "proposal": self.trigger_index, "preview_token": preview["preview_token"]}
        for _ in range(2):
            response = self.client.post(route + "/bulk", headers=self.csrf, json=body)
            self.assertEqual(response.status_code, 200, response.text)
        records = response.json()["result"]["records"]
        statuses = {r["source_file_id"]: r.get("status") for r in records}
        self.assertEqual([statuses[file] for file in files], ["rejected"] * 3 + [None])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            events = c.execute("SELECT e.*,a.identifier FROM attention_events e JOIN attention_items a ON a.id=e.item_id WHERE a.task_id=%s AND e.action='bulk_decision'", (run["task_id"],)).fetchall()
        self.assertEqual(len(events), 3)
        self.assertEqual({e["identifier"] for e in events}, {f"bulk-{i}.pdf" for i in range(3)})
        self.assertTrue(all(str(e["actor_id"]) == response.json()["actor_id"] and e["detail"]["count"] == 3
                            and e["detail"]["trigger_file_id"] == files[0] and e["detail"]["subject"]["company_guid"] == "bulk-company" for e in events))

    def test_stale_preview_and_unsupported_grouping_never_apply_a_partial_decision(self):
        run, files, route = self.group()
        preview = self.preview(route, "nothing")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            result = c.execute("SELECT result FROM account_runs WHERE id=%s", (run["id"],)).fetchone()["result"]
            next(r for r in result["records"] if r["source_file_id"] == files[1])["document"]["supplier_name"] = "Changed Supplier"
            c.execute("UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(result), run["id"]))
        response = self.client.post(route + "/bulk", headers=self.csrf, json={"action": "nothing", "proposal": self.trigger_index, "preview_token": preview["preview_token"]})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.client.post(route + "/bulk-preview", headers=self.csrf, json={"action": "guess", "proposal": self.trigger_index}).status_code, 422)
        self.assertEqual(self.client.post(route.replace("mock-tenant", "pr-infra") + "/bulk-preview", headers=self.csrf, json={"action": "nothing", "proposal": self.trigger_index}).status_code, 404)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertFalse(any(r.get("status") == "rejected" for r in loaded["result"]["records"]))

    def test_supplier_bulk_queues_one_creation_and_continues_every_authorized_bill(self):
        run, files, route = self.group()
        preview = self.preview(route, "supplier")
        response = self.client.post(route + "/bulk", headers=self.csrf, json={"action": "supplier", "proposal": self.trigger_index, "preview_token": preview["preview_token"]})
        self.assertEqual(response.status_code, 200, response.text)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            jobs = c.execute("SELECT * FROM desktop_jobs WHERE task_id=%s AND operation='attention.supplier'", (run["task_id"],)).fetchall()
            self.assertEqual(len(jobs), 1)
            item = c.execute("SELECT * FROM attention_items WHERE id=%s", (jobs[0]["input"]["item_id"],)).fetchone()
            self.assertEqual(len(item["target"]["authorized_proposals"]), 3)
            from minkops_platform.accounts.attention import supplier_created
            observation = {"valid": True, "masters": [{"@_NAME": "New Supplier", "GUID": "new-guid", "PARENT": "Sundry Creditors", "ALTERID": "1"}]}
            supplier_created(c, item, jobs[0], observation)
            stored = c.execute("SELECT result FROM account_runs WHERE id=%s", (run["id"],)).fetchone()["result"]
            statuses = {r["source_file_id"]: r.get("status") for r in stored["records"]}
            self.assertEqual([statuses[file] for file in files], ["writing"] * 3 + [None])
            self.assertEqual(c.execute("SELECT count(*) FROM account_tally_writes WHERE run_id=%s", (run["id"],)).fetchone()["count"], 3)
        self.client.post(self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf)

    def test_retry_save_uses_one_approval_and_replay_does_not_enqueue_more_writes(self):
        from unittest.mock import patch
        from minkops_platform.accounts.service import approve_run
        run, files, route = self.group()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            stored = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            for record in stored["result"]["records"]:
                record["data"]["vendor"] = "Supplier"
                record["voucher"]["party"] = {"ledger_guid": "Supplier-guid", "new_supplier": False, "evidence": "Native supplier identity."}
                record.update(status="held", save_hold="Destination unavailable", findings=["Destination unavailable"],
                              save_hold_code="company_not_open" if record["source_file_id"] in files[:3] else "rejected", exception_codes=[])
            c.execute("UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(stored["result"]), run["id"]))
        preview = self.preview(route, "retry_save")
        body = {"action": "retry_save", "proposal": self.trigger_index, "preview_token": preview["preview_token"]}
        with patch("minkops_platform.accounts.service.approve_run", wraps=approve_run) as approve:
            for _ in range(2):
                response = self.client.post(route + "/bulk", headers=self.csrf, json=body)
                self.assertEqual(response.status_code, 200, response.text[:300])
            self.assertEqual(approve.call_count, 1)
        self.assertEqual(len(response.json()["tally_writes"]), 3)
        statuses = {r["source_file_id"]: r.get("status") for r in response.json()["result"]["records"]}
        self.assertEqual([statuses[file] for file in files], ["writing"] * 3 + ["held"])
        self.client.post(self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf)

    def test_bulk_recheck_refreshes_once_and_queues_three_children_in_one_transaction(self):
        from unittest.mock import patch
        from minkops_platform.accounts.bills import refreshed_tally_target
        run, files, route = self.group()
        preview = self.preview(route, "retry")
        with patch("minkops_platform.accounts.bills.refreshed_tally_target", wraps=refreshed_tally_target) as refresh:
            response = self.client.post(route + "/bulk", headers=self.csrf, json={"action": "retry", "proposal": self.trigger_index, "preview_token": preview["preview_token"]})
            self.assertEqual(response.status_code, 200, response.text[:300])
            self.assertEqual(refresh.call_count, 1)
        self.assertEqual(response.json()["state"], "queued")
        with psycopg.connect(URL, row_factory=dict_row) as c:
            children = c.execute("SELECT file_ids,state,config FROM account_runs WHERE parent_run_id=%s", (run["id"],)).fetchall()
        new = [child for child in children if child["state"] == "queued" and not child["config"].get("superseded")]
        self.assertEqual({child["file_ids"][0] for child in new}, set(files[:3]))
        self.assertTrue(any(child["file_ids"][0] == files[3] and not child["config"].get("superseded") for child in children))
        self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control", headers=self.csrf, json={"action": "stop"})

    def test_supplier_callback_while_paused_waits_for_resume_without_losing_consent(self):
        run, _, route = self.group()
        preview = self.preview(route, "supplier")
        response = self.client.post(route + "/bulk", headers=self.csrf, json={"action": "supplier", "proposal": self.trigger_index, "preview_token": preview["preview_token"]})
        self.assertEqual(response.status_code, 200, response.text[:300])
        control = f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control"
        self.assertEqual(self.client.post(control, headers=self.csrf, json={"action": "pause"}).status_code, 200)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            job = c.execute("SELECT * FROM desktop_jobs WHERE task_id=%s AND operation='attention.supplier'", (run["task_id"],)).fetchone()
            item = c.execute("SELECT * FROM attention_items WHERE id=%s", (job["input"]["item_id"],)).fetchone()
            from minkops_platform.accounts.attention import supplier_created
            supplier_created(c, item, job, {"valid": True, "masters": [{"@_NAME": "New Supplier", "GUID": "paused-guid", "PARENT": "Sundry Creditors", "ALTERID": "1"}]})
            self.assertEqual(c.execute("SELECT count(*) AS n FROM account_tally_writes WHERE run_id=%s", (run["id"],)).fetchone()["n"], 0)
            self.assertTrue(c.execute("SELECT target ? 'supplier_continuation' AS pending FROM attention_items WHERE id=%s", (item["id"],)).fetchone()["pending"])
        self.assertEqual(self.client.post(control, headers=self.csrf, json={"action": "resume"}).status_code, 200)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual((loaded["state"], len(loaded["tally_writes"])), ("writing", 3))
        self.client.post(self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf)
