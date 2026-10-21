"""Real database/auth tests; replace only the paid hosted agent boundary."""

import json
import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from test_accounts_excel import catalog, workbook

from minkops_api.main import app

URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class AccountsTests(unittest.TestCase):
    def test_hosted_cleanup_retries_are_bounded_without_claiming_false_success(self):
        from minkops_platform.accounts.worker import STORE

        run, _ = self.launch()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute(
                "UPDATE account_runs SET state='failed',session_id='cleanup-bound-test',updated_at='2000-01-01',config=config || '{\"cleanup_attempt_count\":9}'::jsonb WHERE id=%s",
                (run["id"],),
            )
            claimed = STORE.claim_cleanup(c)
            self.assertEqual(str(claimed["id"]), run["id"])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute(
                'UPDATE account_runs SET config=config || \'{"cleanup_attempt_at":"2000-01-01"}\'::jsonb WHERE id=%s',
                (run["id"],),
            )
            claimed = STORE.claim_cleanup(c)
            self.assertTrue(not claimed or str(claimed["id"]) != run["id"])
            config = c.execute(
                "SELECT config FROM account_runs WHERE id=%s", (run["id"],)
            ).fetchone()["config"]
            self.assertEqual(config["cleanup_attempt_count"], 10)
            self.assertFalse(config.get("hosted_session_closed", False))

    def test_launch_pins_complete_definition_and_replay_keeps_the_original_bundle(self):
        from minkops_platform.runtime.bundles import validate_snapshot
        from minkops_platform.runtime.store import run_for

        run, body = self.launch()
        self.assertNotIn("execution_snapshot", run["config"])
        self.assertNotIn("instructions_snapshot", run["config"])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            pinned = run_for(c, run["tenant_id"], run["id"])
        snapshot = pinned["config"]["execution_snapshot"]
        validate_snapshot(snapshot)
        self.assertEqual(snapshot["definition_version"], run["definition_version"])
        self.assertEqual(snapshot["files"]["SKILL.md"], pinned["config"]["instructions_snapshot"])
        self.assertEqual(
            json.loads(snapshot["files"]["agent-output.schema.json"]),
            pinned["config"]["agent_output_schema"],
        )
        with patch(
            "minkops_platform.accounts.service.load_definition",
            side_effect=AssertionError("new checkout"),
        ):
            replay = self.client.post(self.base + "/runs", headers=self.csrf, json=body)
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertNotIn("execution_snapshot", replay.json()["config"])
        with psycopg.connect(URL, row_factory=dict_row) as c:
            replayed = run_for(c, run["tenant_id"], replay.json()["id"])
        self.assertEqual(replayed["config"]["execution_snapshot"], snapshot)

    def test_worker_respects_an_existing_database_run_lock(self):
        from minkops_platform.accounts.worker import STORE, work_once

        run, _ = self.launch()
        executor = MagicMock()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (run["id"],))
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            with patch.object(STORE, "candidates", return_value=[row]):
                self.assertFalse(work_once(URL, executor=executor))
            c.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (run["id"],))
        executor.assert_not_called()

    def test_invalid_agent_proposal_remains_durable_for_diagnostics(self):
        from jsonschema import ValidationError

        from minkops_platform.accounts.worker import process

        run, _ = self.launch()
        received = {"unexpected": "raw proposal"}
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            with self.assertRaises(ValidationError):
                process(c, row, executor=lambda *a, **k: received)
        with psycopg.connect(URL, row_factory=dict_row) as c:
            saved = c.execute(
                "SELECT result FROM account_runs WHERE id=%s", (run["id"],)
            ).fetchone()
            self.assertEqual(saved["result"], received)

    def test_legacy_unpinned_queued_run_fails_without_calling_the_agent(self):
        from minkops_platform.accounts.worker import STORE, work_once

        run, _ = self.launch()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            c.execute(
                "UPDATE account_runs SET config=(config-'execution_snapshot') #- '{_assets,execution_snapshot}' WHERE id=%s",
                (run["id"],),
            )
            c.commit()
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
        executor = MagicMock()
        with patch.object(STORE, "candidates", return_value=[row]):
            self.assertTrue(work_once(URL, executor=executor))
        executor.assert_not_called()
        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute(
                "SELECT state,error FROM account_runs WHERE id=%s", (run["id"],)
            ).fetchone()
        self.assertEqual(row["state"], "failed")
        self.assertIn("execution bundle", row["error"])

    def setUp(self):
        os.environ["DATABASE_URL"] = URL
        self.client = TestClient(app)
        response = self.client.post(
            "/api/auth/login",
            json={"email": "demo@example.com", "password": "long test password 123!"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.csrf = {"x-csrf-token": self.client.get("/api/auth/me").json()["csrf_token"]}
        self.base = "/api/tenants/mock-tenant/accounts"
        with psycopg.connect(URL) as c:
            # Regression cases use the generic tenant binding; client-specific
            # policy has separate tests.
            from psycopg.types.json import Jsonb

            from minkops_platform.resources import REPOSITORY_ROOT
            from minkops_platform.workflows import load_definition

            definition = load_definition(REPOSITORY_ROOT / 'employees/accounts-desk/workflows/bill-entry')
            # This fixture exercises the unrestricted core variant with explicit
            # review; tests opt into only_exceptions. Dedicated client-composition
            # tests retain the installed mock-client policy and defaults.
            c.execute("""UPDATE workflows SET config_schema=%s,execution_binding=execution_binding-'solution',
                config_values=(config_values - 'output_mode') || '{"review_mode":"all_outputs"}'::jsonb
                WHERE key='bill-entry' AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant')""",
                (Jsonb(definition.tenant_schema),))
            c.execute(
                "UPDATE workflows SET status='active' WHERE key IN ('bill-entry','source-discovery') AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant')"
            )
        response = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={
                "label": "Test folder",
                "writable": "true",
                "paths": json.dumps(["records.xlsx"]),
            },
            files=[("files", ("records.xlsx", workbook()))],
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.source = response.json()
        self.file_id = self.source["files"][0]["id"]

    def launch(self, key="source-discovery", **changes):
        body = {"key": key, "request_key": str(uuid.uuid4()), "file_ids": [self.file_id], **changes}
        response = self.client.post(self.base + "/runs", headers=self.csrf, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json(), body

    def execute_discovery(self):
        run, _ = self.launch()
        expected = catalog()
        expected["sheets"][0]["file_id"] = self.file_id
        expected["sheets"].append(
            {
                "file_id": self.file_id,
                "sheet": "Other",
                "header_row": 1,
                "role": "ignore",
                "key_columns": [],
                "columns": [
                    {"name": "Keep me", "type": "string", "concept": "", "required": False}
                ],
            }
        )

        def fake(key, files, context, event, **kwargs):
            event("agent.session.turn.created", "session-test", "turn-test")
            return expected

        # Explicitly process this test's run, independent of other queued work.
        from minkops_api.accounts_worker import process

        with psycopg.connect(URL, row_factory=dict_row) as c:
            row = c.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
            process(c, row, executor=fake)
        response = self.client.post(
            self.base + f"/runs/{run['id']}/approve", headers=self.csrf, json={"result": expected}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["catalog_id"]

    def test_launch_idempotency_and_tenant_isolation(self):
        run, body = self.launch()
        again = self.client.post(self.base + "/runs", headers=self.csrf, json=body)
        self.assertEqual(again.json()["id"], run["id"])
        changed = {**body, "config": {"max_files": 2}}
        self.assertEqual(
            self.client.post(self.base + "/runs", headers=self.csrf, json=changed).status_code, 409
        )
        self.assertEqual(
            self.client.get("/api/tenants/pr-infra/accounts/runs/" + run["id"]).status_code, 404
        )
        self.assertEqual(self.client.post(self.base + "/runs", json=body).status_code, 403)

    def test_invented_catalog_and_path_traversal_rejected(self):
        run, _ = self.launch()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE account_runs SET state='review' WHERE id=%s", (run["id"],))
        bad = catalog()
        bad["sheets"][0]["file_id"] = self.file_id
        bad["sheets"][0]["sheet"] = "Invented"
        self.assertEqual(
            self.client.post(
                self.base + f"/runs/{run['id']}/approve", headers=self.csrf, json={"result": bad}
            ).status_code,
            422,
        )
        response = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"paths": '["../outside.xlsx"]'},
            files=[("files", ("x.xlsx", workbook()))],
        )
        self.assertEqual(response.status_code, 422)

    def test_stop_during_hosted_work_keeps_raw_output_without_starting_review(self):
        from minkops_platform.accounts.worker import process
        run, _ = self.launch()
        raw = catalog()
        raw["sheets"][0]["file_id"] = self.file_id

        def executor(*args, **kwargs):
            response = self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control",
                                        headers=self.csrf, json={"action": "stop"})
            self.assertEqual(response.status_code, 200, response.text)
            return raw

        with psycopg.connect(URL, row_factory=dict_row) as connection:
            process(connection, connection.execute("SELECT * FROM workflow_runs WHERE id=%s", (run["id"],)).fetchone(), executor=executor)
        stopped = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(stopped["result"], raw)
        self.assertEqual(stopped["tally_writes"], [])
