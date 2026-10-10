"""Discovery owns reference evidence; new bill runs have no schema search job."""

import json
import os
import uuid
import unittest
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

    def test_metadata_only_catalog_requires_complete_rediscovery(self):
        discovery = self.tally_discovery("company-1", schema=True)
        response = self.client.post(
            self.base + "/runs",
            headers=self.csrf,
            json={
                "key": "bill-entry",
                "request_key": uuid.uuid4().hex,
                "file_ids": [self.upload_bill()],
                "config": {"output_mode": "tally_in_place", "discovery_id": discovery},
            },
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("complete company context", response.text)

    def test_hosted_dispatch_reads_committed_launch_without_reference_job(self):
        discovery = self.tally_discovery("company-1")
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
            run, _ = self.launch(
                "bill-entry",
                file_ids=[self.upload_bill()],
                config={"output_mode": "tally_in_place", "discovery_id": discovery},
            )
        self.assertEqual(calls, [1])
        self.assertNotIn("tally_context_job_id", run["config"])
        self.assertIsNone(
            self.client.post("/api/desktop/worker/claim", headers=self.worker, json={}).json()
        )

    def test_full_evidence_is_pinned_in_lookup_files_and_device_archive_is_scoped(self):
        from minkops_platform.accounts.handlers import BillHandler

        discovery = self.tally_discovery("company-1")
        run, _ = self.launch(
            "bill-entry",
            file_ids=[self.upload_bill()],
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        with psycopg.connect(URL, row_factory=dict_row) as c:
            saved = c.execute("SELECT * FROM workflow_runs WHERE id=%s", (run["id"],)).fetchone()
            files, context, _ = BillHandler().prepare(c, saved)
        self.assertEqual(context["source_catalog"]["run_id"], discovery)
        self.assertNotIn("records", json.dumps(context["source_catalog"]))
        assets = [f for f in files if str(f["id"]).startswith("discovery-")]
        self.assertTrue(any("Supplier" in bytes(f["content"]).decode() for f in assets))
        self.assertNotIn("source_catalog_snapshot", context["config"])
        archive = self.client.get("/api/desktop/discovery/package", headers=self.worker)
        self.assertEqual(archive.status_code, 200, archive.text)
        self.assertEqual(archive.json()["run_id"], discovery)
        self.assertEqual(self.client.get("/api/desktop/discovery/package").status_code, 401)

    def test_explicit_retry_refreshes_context_but_rejects_company_replacement(self):
        discovery = self.tally_discovery("company-1")
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
                "findings": [],
                "unresolved": [{"source_file_id": bill, "reason": "Supplier missing"}],
            },
        )
        self.tally_discovery("company-2", reuse_device=True)
        response = self.client.post(
            self.base + f"/runs/{run['id']}/resolve-bill",
            headers=self.csrf,
            json={"file_id": bill, "user_input": "Continue", "reject": False},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("Company scope changed", response.text)

    def test_identical_refresh_retains_notes_and_archives_each_version_once(self):
        from psycopg.types.json import Jsonb

        first = self.tally_discovery("company-1")
        note = {
            "company_guid": "company-1",
            "observation": "An obscure supplier convention",
            "evidence_ids": ["Supplier"],
            "certainty": "observed",
        }
        with psycopg.connect(URL) as c:
            c.execute(
                "UPDATE discovery_runs SET catalog=jsonb_set(catalog,'{context_notes}',%s) WHERE id=%s",
                (Jsonb([note]), first),
            )
        second = self.tally_discovery("company-1", reuse_device=True)
        initial = self.client.get("/api/desktop/discovery/package", headers=self.worker)
        self.assertEqual(initial.json()["run_id"], first)
        self.assertIn("no-store", initial.headers["cache-control"])
        refreshed = self.client.get(
            "/api/desktop/discovery/package?after_id=" + first, headers=self.worker
        ).json()
        self.assertEqual(refreshed["run_id"], second)
        self.assertEqual(refreshed["context_notes"], [note])
        self.assertIsNone(
            self.client.get(
                "/api/desktop/discovery/package?after_id=" + second, headers=self.worker
            ).json()
        )
