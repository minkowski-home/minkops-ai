"""The GST capability is pinned, version-gated and verified before continuation."""
import unittest

import psycopg
import test_bill_entry as bills
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

URL = bills.URL


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class GSTSupplierTests(unittest.TestCase):
    setUp = bills.BillEntryTests.setUp
    launch = bills.BillEntryTests.launch
    execute_discovery = bills.BillEntryTests.execute_discovery
    tally_discovery = bills.BillEntryTests.tally_discovery
    upload_bill = bills.BillEntryTests.upload_bill
    tally_result = bills.BillEntryTests.tally_result
    process = bills.BillEntryTests.process

    def test_native_registration_readback_is_required_and_old_companions_get_no_plan(self):
        discovery = self.tally_discovery("company-gst")
        bill = self.upload_bill()
        run, _ = self.launch("bill-entry", file_ids=[bill], config={
            "output_mode": "tally_in_place", "discovery_id": discovery})
        template = {"type": "LEDGER", "data": {"NAME": "Registered supplier", "GUID": "template",
            "ALTERID": "1", "PARENT": "Sundry Creditors", "PARTYGSTIN": "27AAPFU0939F1ZV", "GSTREGISTRATIONTYPE": "Regular"}}
        with psycopg.connect(URL, row_factory=dict_row) as c:
            from minkops_platform.accounts.repository import run_for
            config = run_for(c, run["tenant_id"], run["id"])["config"]
            company = config["source_catalog_snapshot"]["sources"][0]["snapshot"]["companies"][0]
            company["identity"]["STATENAME"] = "Maharashtra"
            company["masters"]["records"].append(template)
            from minkops_platform.accounts.client_context import context_assets
            from minkops_platform.accounts.repository import files_for
            assets, _ = context_assets(config["source_catalog_snapshot"])
            config["authorized_bindings"] = [b for b in config["authorized_bindings"] if b["capability"] != "files.snapshot"] + [
                {"capability": "files.snapshot", "resource_id": str(f["id"]), "sha256": f["sha256"]}
                for f in [*files_for(c, run["tenant_id"], [bill]), *assets]]
            c.execute("UPDATE account_runs SET config=%s WHERE id=%s", (Jsonb(config), run["id"]))
        result = self.tally_result(run, bill)
        row = result["records"][0]
        row["document"]["supplier_name"] = "Synthetic GST supplier"
        row["voucher"]["party"] = {"ledger_guid": None, "new_supplier": True, "evidence": "No discovered supplier matches printed identifiers."}
        row["supplier_details"] = {"gstin": "27AABCM1256F1ZR", "registration_type": "Regular", "state_code": "27",
            "state": "Maharashtra", "place_of_supply": "Maharashtra (27)", "address": ["Synthetic Road", "Pune"], "pincode": "411001",
            "evidence": [{"field": key, "page": 1, "quote": text} for key, text in {
                "gstin": "27AABCM1256F1ZR", "registration_type": "Regular", "state": "Maharashtra",
                "place_of_supply": "Maharashtra (27)", "address": "Synthetic Road, Pune 411001"}.items()]}
        row["evidence"] = [e for e in row["evidence"] if e["field"] != "supplier"] + [{"field": "supplier", "page": 1, "quote": "Synthetic GST supplier"}]
        self.process(run, result)
        offered = self.client.get(self.base + f"/runs/{run['id']}").json()["result"]["records"][0]
        self.assertIn("supplier", offered["allowed_actions"])
        self.assertEqual(offered["unavailable_actions"], {})
        route = f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}"
        decision = self.client.post(route, headers=self.csrf, json={"action": "supplier"})
        self.assertEqual(decision.status_code, 200, decision.text)
        job = self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        plan_route = f"/api/desktop/worker/jobs/{job['id']}/plan?claim_token={job['claim_token']}"
        self.assertEqual(self.client.get(plan_route, headers={**self.worker, "X-Minkops-Plan-Version": "4"}).status_code, 409)
        plan = self.client.get(plan_route, headers={**self.worker, "X-Minkops-Plan-Version": "5"})
        self.assertEqual(plan.status_code, 200, plan.text)
        self.assertEqual(plan.json()["gst_supplier"]["gstin"], "27AABCM1256F1ZR")
        master = {"NAME": "Synthetic GST supplier", "GUID": "created", "ALTERID": "2", "PARENT": "Sundry Creditors"}
        full = {**master, "GUID": {"#text": "created"}, "PARENT": {"#text": "Sundry Creditors"},
                "PARTYGSTIN": "27AABCM1256F1ZR", "GSTREGISTRATIONTYPE": "Regular", "LEDSTATENAME": "Maharashtra",
                "PLACEOFSUPPLY": "Maharashtra", "PINCODE": "411001", "ADDRESS.LIST": {"ADDRESS": ["Synthetic Road", "Pune"]}}
        finished = self.client.post(f"/api/desktop/worker/jobs/{job['id']}/finish", headers=self.worker, json={
            "claim_token": job["claim_token"], "result": {"company_guid": "company-gst", "ledgers": [master], "supplier": full, "current": None}})
        self.assertEqual(finished.status_code, 200, finished.text)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"], "writing", loaded.get("result"))

