"""Company-scoped bill sessions and generic workflow stages."""

import unittest

from minkops_platform.accounts import company_scope
from minkops_platform.accounts.client_context import context_assets
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.runtime.bundles import stage_schema, stages, validate_snapshot
from minkops_platform.workflows import load_definition


def company(name, guid, *, gstin=None, books=None, vouchers=0, padding=0, supplier_gstin=None):
    identity = {"NAME": name, "GUID": guid, **({"GSTIN": gstin} if gstin else {}), **({"BOOKSFROM": books} if books else {})}
    masters = [{"type": "LEDGER", "data": {"NAME": "Acme", "GUID": f"{guid}-acme", "PARENT": "Sundry Creditors",
                                           **({"PARTYGSTIN": supplier_gstin} if supplier_gstin else {})}}]
    records = [{"type": "VOUCHER", "data": {"GUID": f"{guid}-v{i}", "DATE": f"2026{(i % 9) + 1:02d}01",
                                            "PARTYLEDGERNAME": "Acme" if i % 5 == 0 else "Other", "NARRATION": "x" * padding}}
               for i in range(vouchers)]
    return {"company": name, "company_guid": guid, "identity": identity, "port": 9000, "status": "ready",
            "masters": {"status": "ready", "count": len(masters), "records": masters},
            "vouchers": {"status": "ready", "count": len(records), "records": records}}


def catalog(*companies):
    return {"format_version": "2", "master_lookup_version": "1", "run_id": "run", "context_notes": [],
            "sources": [{"tool": "tally", "key": "tally", "snapshot": {"period": {}, "companies": list(companies)}}]}


class StageTest(unittest.TestCase):
    def test_bill_entry_pins_its_triage_stage_inside_the_same_bundle(self):
        definition = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry")
        snapshot = definition.execution_snapshot
        self.assertEqual(set(stages(snapshot)), {"triage", "posting_profile"})
        self.assertIn("stages/triage.md", snapshot["files"])
        self.assertEqual(stage_schema(snapshot, "triage")["required"], ["bills"])
        broken = {**snapshot, "files": {k: v for k, v in snapshot["files"].items() if k != "stages/triage.md"}}
        from minkops_platform.runtime.bundles import digest
        broken["sha256"] = digest(broken)
        with self.assertRaises(ValueError):
            validate_snapshot(broken)

    def test_a_stage_changes_only_the_execution_instructions(self):
        from unittest import mock

        from minkops_platform.runtime import workflow

        snapshot = load_definition(REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry").execution_snapshot
        with mock.patch.object(workflow, "hosted_execute", return_value={}) as hosted:
            workflow.execute("bill-entry", [], {"config": {"execution_snapshot": snapshot, "stage": "triage"}}, None)
            workflow.execute("bill-entry", [], {"config": {"execution_snapshot": snapshot}}, None)
        triage, posting = (call.kwargs for call in hosted.call_args_list)
        self.assertEqual(triage["instructions"], posting["instructions"])
        self.assertTrue(triage["execution_instructions"].startswith("Routing stage."))
        self.assertEqual(posting["execution_instructions"], snapshot["files"]["execution-instructions.md"])


class DirectoryTest(unittest.TestCase):
    def test_year_split_companies_are_siblings_with_consecutive_periods(self):
        entries = {e["company_guid"]: e for e in company_scope.directory(catalog(
            company("Sachin (2025-26)", "a", gstin="27AAACS1234A1Z5", books="20250401"),
            company("Sachin (2026-27)", "b", gstin="27AAACS1234A1Z5", books="20260401"),
            company("Other", "c", gstin="29BBBCS1234A1Z5", books="20250401")))}
        self.assertEqual((entries["a"]["siblings"], entries["a"]["period_to"]), (["b"], "2026-03-31"))
        self.assertEqual((entries["b"]["siblings"], entries["b"]["period_to"]), (["a"], None))
        self.assertEqual((entries["c"]["siblings"], entries["c"]["period_to"]), ([], None))

    def test_routing_moves_a_bill_only_to_the_one_sibling_covering_its_date(self):
        routes = {"a": {"company": "2025-26", "references": {"company_guid": "a"}, "books_from": "2025-04-01",
                        "period_to": "2026-03-31", "siblings": ["b"]},
                  "b": {"company": "2026-27", "references": {"company_guid": "b"}, "books_from": "2026-04-01",
                        "period_to": None, "siblings": ["a"]}}
        def entry(guid, issued):
            return {"company_guid": guid, "documents": [{"date": issued}], "exception": None}
        self.assertEqual(company_scope.route(entry("a", "2026-02-01"), routes), ("a", None))
        moved, note = company_scope.route(entry("a", "2026-10-01"), routes)
        self.assertEqual(moved, "b")
        self.assertIn("routed from 2025-26", note)
        self.assertEqual(company_scope.route(entry("b", "2024-01-01"), routes)[1][0], "date_outside_company_period")
        self.assertEqual(company_scope.route(entry("z", "2026-01-01"), routes)[1][0], "company_unresolved")
        self.assertEqual(company_scope.route({"company_guid": None, "exception": {"code": "not_a_bill", "detail": "Quote"}}, routes),
                         (None, ("not_a_bill", "Quote")))

    def test_triage_chunks_respect_file_and_byte_limits(self):
        files = [{"id": i, "content": b"x" * 400_000} for i in range(45)]
        chunks = company_scope.triage_chunks(files)
        self.assertEqual([len(c) for c in chunks], [18, 18, 9])
        self.assertEqual(sum(chunks, []), [str(i) for i in range(45)])


class ScopedAssetsTest(unittest.TestCase):
    def test_posting_child_pins_only_routed_company_without_copying_other_native_records(self):
        class Uncopyable(dict):
            def __deepcopy__(self, memo):
                raise AssertionError('Unrelated company evidence was copied')
        a, b = company('A', 'a'), Uncopyable(company('B', 'b'))
        whole = catalog(a, b)
        whole['sources'][0]['snapshot']['company_scope'] = [
            {'company_guid': 'a'}, {'company_guid': 'b'}]
        config = {'source_catalog_snapshot': whole, 'tally_target': {'companies': [
            {'references': {'company_guid': 'a'}}, {'references': {'company_guid': 'b'}}]}}
        child = company_scope.scoped_config(config, 'a')
        observed = child['source_catalog_snapshot']['sources'][0]['snapshot']
        self.assertEqual(observed['companies'], [a])
        self.assertEqual(observed['company_scope'], [{'company_guid': 'a'}])
        self.assertEqual(len(whole['sources'][0]['snapshot']['companies']), 2)
        self.assertEqual(context_assets(whole, companies=['a'])[0],
                         context_assets(child['source_catalog_snapshot'], companies=['a'])[0])

    def test_one_company_is_delivered_with_its_supplier_history_first_when_over_budget(self):
        whole = catalog(company("A", "a", vouchers=40, padding=20_000, supplier_gstin="27AAACA0000A1Z5"),
                        company("B", "b", vouchers=40, padding=20_000))
        full, manifest = context_assets(whole, companies=["a"])
        self.assertEqual([c["company_guid"] for c in manifest["companies"]], ["a"])
        self.assertNotIn("vouchers_from", manifest["companies"][0])
        budget = 300_000
        bounded, manifest = context_assets(whole, companies=["a"], voucher_budget=budget, supplier_gstins=["27AAACA0000A1Z5"])
        import json
        vouchers = [r for a in bounded if "-vouchers-" in a["path"] for r in json.loads(a["content"])]
        self.assertLessEqual(sum(len(json.dumps(r)) for r in vouchers), budget)
        self.assertEqual(sum(v["data"]["PARTYLEDGERNAME"] == "Acme" for v in vouchers), 8)  # Every supplier voucher kept.
        self.assertIn("vouchers_from", manifest["companies"][0])
        # Masters are never sampled.
        masters = [a for a in bounded if "-masters-" in a["path"]]
        self.assertEqual(sum(len(json.loads(a["content"])) for a in masters), 1)


if __name__ == "__main__":
    unittest.main()
