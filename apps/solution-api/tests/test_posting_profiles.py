"""A company's posting pattern: derived once, confirmed once, reused by every later bill."""
import unittest

import psycopg
import test_bill_entry as bills
from psycopg.rows import dict_row

URL = bills.URL


def payload(company_guid, voucher_type="Purchase-guid"):
    return {"company_guid": company_guid,
            "families": {"invoice": {"family": "purchase", "voucher_type_guid": voucher_type}, "credit_note": None},
            "invoice_number": {"fields": ["REFERENCE"]}, "round_off": None, "tds": None,
            "party_groups": ["Sundry Creditors"],
            "practice": [{"statement": "Purchases post to Purchases.", "evidence_vouchers": []}],
            "summary": ["Purchases: Purchase", "Supplier invoice number in Reference"]}


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class PostingProfileTests(unittest.TestCase):
    for _method in ("setUp", "launch", "upload_bill", "process", "tally_discovery", "tally_result", "approve"):
        locals()[_method] = getattr(bills.BillEntryTests, _method)

    def run_row(self, run_id):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            return c.execute("SELECT * FROM account_runs WHERE id=%s", (run_id,)).fetchone()

    def derivations(self, run_id):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            return c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s AND config->>'stage'='posting_profile'",
                             (run_id,)).fetchall()

    def card(self, task_id):
        with psycopg.connect(URL, row_factory=dict_row) as c:
            return c.execute("SELECT * FROM attention_items WHERE task_id=%s AND kind='profile'", (task_id,)).fetchone()

    def launch_bill(self, did, name="bill.pdf", **config):
        bill = self.upload_bill(name)
        run, _ = self.launch("bill-entry", file_ids=[bill], catalog_id=None,
                             config={"output_mode": "tally_in_place", "discovery_id": did, **config})
        return run, bill

    def test_the_first_bill_waits_for_one_confirmation_and_later_bills_reuse_it(self):
        did = self.tally_discovery("pattern-co", confirmed_patterns=False)
        run, bill = self.launch_bill(did)
        waiting = self.run_row(run["id"])
        self.assertIn("awaits", waiting["config"])
        [derivation] = self.derivations(run["id"])
        self.assertEqual((derivation["file_ids"], derivation["config"]["company_scope"]), ([], ["pattern-co"]))
        self.process(derivation, payload("pattern-co"))
        card = self.card(run["task_id"])
        self.assertEqual((card["status"], card["label"], card["target"]["waiting"]), ("pending", "Confirm posting pattern", 1))
        self.assertIn("Purchases: Purchase", card["target"]["summary"])
        listed = next(i for i in self.client.get("/api/tenants/mock-tenant/attention").json() if i["id"] == str(card["id"]))
        self.assertEqual(listed["profile"], {"company": "Test", "summary": card["target"]["summary"], "waiting": 1})
        self.assertNotIn("target", listed)
        decided = self.client.post(f"/api/tenants/mock-tenant/attention/{card['id']}/profile", headers=self.csrf,
                                   json={"action": "confirm"})
        self.assertEqual(decided.status_code, 200, decided.text)
        released = self.run_row(run["id"])
        self.assertNotIn("awaits", released["config"])
        self.assertEqual(released["config"]["posting_profiles"]["pattern-co"]["summary"][0], "Purchases: Purchase")
        self.process(released, self.tally_result(run, bill))
        self.assertEqual(self.client.get(self.base + f"/runs/{run['id']}").json()["state"], "review")
        # The next bill for the company starts with the confirmed pattern.
        later, _ = self.launch_bill(did, "later.pdf")
        self.assertIn("pattern-co", self.run_row(later["id"])["config"]["posting_profiles"])
        self.assertEqual(self.derivations(later["id"]), [])
        again = self.client.post(f"/api/tenants/mock-tenant/attention/{card['id']}/profile", headers=self.csrf,
                                 json={"action": "confirm"})
        self.assertEqual(again.status_code, 409)

    def test_do_nothing_leaves_waiting_bills_for_manual_entry(self):
        did = self.tally_discovery("declined-co", confirmed_patterns=False)
        run, _ = self.launch_bill(did)
        self.process(self.derivations(run["id"])[0], payload("declined-co"))
        card = self.card(run["task_id"])
        self.client.post(f"/api/tenants/mock-tenant/attention/{card['id']}/profile", headers=self.csrf, json={"action": "nothing"})
        held = self.run_row(run["id"])
        self.assertEqual(held["state"], "failed")
        self.assertIn("not confirmed", held["error"])

    def test_concurrent_runs_share_one_derivation(self):
        did = self.tally_discovery("shared-co", confirmed_patterns=False)
        first, _ = self.launch_bill(did, "one.pdf")
        second, _ = self.launch_bill(did, "two.pdf")
        self.assertEqual(len(self.derivations(first["id"])) + len(self.derivations(second["id"])), 1)
        self.assertEqual(self.run_row(first["id"])["config"]["awaits"], self.run_row(second["id"])["config"]["awaits"])

    def test_an_invalid_pattern_fails_its_derivation_and_releases_the_scope(self):
        from minkops_platform.accounts.batch import reconcile_once
        did = self.tally_discovery("broken-co", confirmed_patterns=False)
        run, _ = self.launch_bill(did)
        derivation = self.derivations(run["id"])[0]
        with self.assertRaisesRegex(ValueError, "undiscovered voucher type"):
            self.process(derivation, payload("broken-co", voucher_type="not-a-type"))
        # As the worker does for any processing error.
        from minkops_platform.runtime.store import WorkflowRunStore
        with psycopg.connect(URL, row_factory=dict_row) as c:
            WorkflowRunStore().fail(c, self.run_row(derivation["id"]), "The posting pattern names an undiscovered voucher type.")
        reconcile_once(URL)
        self.assertEqual(self.run_row(run["id"])["state"], "failed")
        retry, _ = self.launch_bill(did, "retry.pdf")
        self.assertEqual(len(self.derivations(retry["id"])), 1, "A failed derivation never blocks the next need.")

    def test_a_year_split_sibling_inherits_a_confirmed_pattern_without_asking_again(self):
        from minkops_platform.accounts.posting_profiles import validate
        from minkops_platform.accounts.vouchers import Masters
        did = self.tally_discovery("alpha-guid", multiple=True, siblings=True, confirmed_patterns=False)
        from minkops_platform import profiles
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute("SELECT tenant_id,catalog FROM discovery_runs WHERE id=%s", (did,)).fetchone()
            alpha = row["catalog"]["sources"][0]["snapshot"]["companies"][0]
            # Other tests may have confirmed patterns for these fixture companies.
            c.execute("""UPDATE client_profiles SET status='superseded' WHERE tenant_id=%s AND scope_key IN ('alpha-guid','beta-guid')
                AND status IN ('deriving','proposed','active')""", (row["tenant_id"],))
            profiles.create(c, row["tenant_id"], "posting_profile", "alpha-guid",
                            validate(payload("alpha-guid"), Masters(alpha), "alpha-guid"), status="active", actor=None,
                            provenance={"discovery_id": str(did)})
        run, _ = self.launch_bill(did, company_mode="locked", locked_company_guid="beta-guid")
        config = self.run_row(run["id"])["config"]
        self.assertNotIn("awaits", config)
        self.assertEqual(config["posting_profiles"]["beta-guid"]["company_guid"], "beta-guid")
        self.assertEqual(self.derivations(run["id"]), [])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            inherited = c.execute("SELECT provenance FROM client_profiles WHERE scope_key='beta-guid' AND status='active'").fetchone()
        self.assertIn("carried_from", inherited["provenance"])


if __name__ == "__main__":
    unittest.main()
