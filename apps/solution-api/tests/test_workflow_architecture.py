"""Temporary definitions prove the full lifecycle without shipping a new workflow."""

import json
import os
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import psycopg
import test_accounts_api as accounts
import test_bill_entry as bills
from minkops_platform.accounts.worker import process
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import load_definition, register_workflow
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class WorkflowArchitectureTests(unittest.TestCase):
    setUp = accounts.AccountsTests.setUp
    launch = accounts.AccountsTests.launch
    execute_discovery = accounts.AccountsTests.execute_discovery

    def temporary_definition(self, handler="accounts.discovery"):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        key = "temporary-architecture-check"
        directory = root / "employees/accounts-desk/workflows" / key
        shutil.copytree(
            REPOSITORY_ROOT / "employees/accounts-desk/workflows/source-discovery", directory
        )
        metadata = json.loads((directory / "workflow.json").read_text())
        metadata.update(
            key=key,
            handler=handler,
            presentation="accounts-discovery" if handler == "accounts.discovery" else "proposal",
        )
        if handler == "skill.proposal":
            for name in ("tenant-config.schema.json", "run-config.schema.json"):
                (directory / name).write_text(
                    json.dumps({"type": "object", "properties": {}, "additionalProperties": False})
                )
            schema = {
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
                "additionalProperties": False,
            }
            for name in ("output.schema.json", "agent-output.schema.json"):
                (directory / name).write_text(json.dumps(schema))
            metadata.update(tenant_defaults={}, run_defaults={})
        (directory / "workflow.json").write_text(json.dumps(metadata))
        definition = load_definition(directory)
        with psycopg.connect(URL) as connection:
            tenant_id = connection.execute(
                "SELECT id FROM tenants WHERE slug='mock-tenant'"
            ).fetchone()[0]
            workflow_id = register_workflow(connection, tenant_id, definition)
            connection.execute("UPDATE workflows SET status='active' WHERE id=%s", (workflow_id,))

        def remove_fixture():
            with psycopg.connect(URL) as connection:
                # Fixture has no external writes or discovery catalogs. Remove
                # tasks before workflow; all task/run history is test-only.
                connection.execute(
                    "DELETE FROM workflow_runs WHERE tenant_id=%s AND workflow_key=%s",
                    (tenant_id, key),
                )
                connection.execute(
                    "DELETE FROM tasks WHERE tenant_id=%s AND workflow_id=%s",
                    (tenant_id, workflow_id),
                )
                connection.execute(
                    "DELETE FROM workflows WHERE tenant_id=%s AND id=%s", (tenant_id, workflow_id)
                )

        self.addCleanup(remove_fixture)
        return root, key

    def test_renamed_existing_workflow_launches_and_validates_without_core_edits(self):
        root, key = self.temporary_definition()
        with patch("minkops_platform.runtime.launch.REPOSITORY_ROOT", root):
            run, _ = self.launch(key)
        self.assertEqual(run["config"]["runtime_binding"]["handler"], "accounts.discovery")
        expected = accounts.catalog()
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
        with psycopg.connect(URL, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE id=%s", (run["id"],)
            ).fetchone()
            process(connection, row, executor=lambda *a, **k: expected)
        self.assertEqual(
            self.client.get(self.base + f"/runs/{run['id']}").json()["state"], "review"
        )
        approved = self.client.post(
            self.base + f"/runs/{run['id']}/approve", headers=self.csrf, json={"result": expected}
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["state"], "completed")

    def test_default_skill_handler_completes_review_and_rejects_invalid_output(self):
        root, key = self.temporary_definition("skill.proposal")
        with patch("minkops_platform.runtime.launch.REPOSITORY_ROOT", root):
            run, _ = self.launch(key)
        with psycopg.connect(URL, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE id=%s", (run["id"],)
            ).fetchone()
            process(connection, row, executor=lambda *a, **k: {"summary": "Inspected input"})
        invalid = self.client.post(
            self.base + f"/runs/{run['id']}/approve",
            headers=self.csrf,
            json={"result": {"invented": True}},
        )
        self.assertEqual(invalid.status_code, 422)
        approved = self.client.post(
            self.base + f"/runs/{run['id']}/approve",
            headers=self.csrf,
            json={"result": {"summary": "Inspected input"}},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["state"], "completed")
        self.assertEqual(approved.json()["writes"], [])

    def test_request_cannot_inject_a_handler_or_resource_grant(self):
        for field in ("runtime_binding", "authorized_bindings", "execution_snapshot"):
            response = self.client.post(
                self.base + "/runs",
                headers=self.csrf,
                json={
                    "key": "source-discovery",
                    "request_key": str(accounts.uuid.uuid4()),
                    "file_ids": [self.file_id],
                    "config": {field: {}},
                },
            )
            self.assertEqual(response.status_code, 422, response.text)

    def test_client_guardrail_blocks_auto_write_then_allows_explicit_review(self):
        catalog_id = self.execute_discovery()
        bill_id = self.client.post(
            self.base + "/sources",
            headers=self.csrf,
            data={"paths": '["bill.pdf"]'},
            files=[("files", ("bill.pdf", b"%PDF-1.4 test"))],
        ).json()["files"][0]["id"]
        with psycopg.connect(URL) as connection:
            connection.execute(
                """UPDATE workflows SET execution_binding=jsonb_set(execution_binding,'{policies}',%s)
                WHERE tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant') AND key='bill-entry'""",
                (
                    Jsonb(
                        [
                            {
                                "key": "review-threshold",
                                "config": {"field": "Amount", "amount": 50000},
                            }
                        ]
                    ),
                ),
            )
        self.addCleanup(self.clear_policy)
        run, _ = self.launch(
            "bill-entry",
            file_ids=[bill_id],
            catalog_id=catalog_id,
            config={"review_mode": "only_exceptions", "checks": ["duplicate"]},
        )
        result = {
            "records": [
                {
                    "source_file_id": bill_id,
                    "destination_file_id": self.file_id,
                    "sheet": "Bills",
                    "operation": "append",
                    "data": {"Invoice": "POLICY-1", "Vendor": "Acme", "Amount": 50001},
                    "evidence": [
                        {"field": k, "page": 1, "quote": str(v)}
                        for k, v in {
                            "Invoice": "POLICY-1",
                            "Vendor": "Acme",
                            "Amount": 50001,
                        }.items()
                    ],
                    "findings": [],
                }
            ],
            "findings": [],
        }
        with psycopg.connect(URL, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE id=%s", (run["id"],)
            ).fetchone()
            process(connection, row, executor=lambda *a, **k: result)
        loaded = self.client.get(self.base + f"/runs/{run['id']}").json()
        self.assertEqual(loaded["state"], "review")
        self.assertEqual(loaded["writes"], [])
        self.assertTrue(loaded["result"]["requires_review"])
        self.clear_policy()  # Existing run retains its pinned policy after reinstall/change.
        approved = self.client.post(
            self.base + f"/runs/{run['id']}/approve",
            headers=self.csrf,
            json={"result": loaded["result"], "acknowledge_findings": True},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["state"], "writing")
        self.client.post(self.base + f"/runs/{run['id']}/cancel-writes", headers=self.csrf)

    def clear_policy(self):
        with psycopg.connect(URL) as connection:
            connection.execute("""UPDATE workflows SET execution_binding=jsonb_set(execution_binding,'{policies}','[]')
                WHERE tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant') AND key='bill-entry'""")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class UnifiedBillArchitectureTests(unittest.TestCase):
    setUp = accounts.AccountsTests.setUp
    launch = accounts.AccountsTests.launch
    upload_bill = bills.BillEntryTests.upload_bill
    tally_discovery = bills.BillEntryTests.tally_discovery
    tally_result = bills.BillEntryTests.tally_result
    approve = bills.BillEntryTests.approve
    process = bills.BillEntryTests.process
    clear_policy = WorkflowArchitectureTests.clear_policy

    def test_batch_keeps_installed_binding_policy_and_single_parent_observation(self):
        from minkops_platform.accounts.batch import reconcile_once
        from minkops_platform.accounts.worker import STORE
        from minkops_platform.runtime.store import WorkflowRunStore

        self.assertIsInstance(STORE, WorkflowRunStore)
        discovery = self.tally_discovery()
        inputs = [self.upload_bill("first.pdf"), self.upload_bill("second.pdf")]
        policies = [{"key": "review-threshold", "config": {"field": "total", "amount": 100}}]
        with psycopg.connect(URL) as connection:
            connection.execute(
                """UPDATE workflows SET execution_binding=jsonb_set(execution_binding,'{policies}',%s)
                WHERE tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant') AND key='bill-entry'""",
                (Jsonb(policies),),
            )
        self.addCleanup(self.clear_policy)
        parent, _ = self.launch(
            "bill-entry",
            file_ids=inputs,
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        self.assertTrue(parent["config"]["batch"])
        with psycopg.connect(URL, row_factory=dict_row) as connection:
            children = connection.execute(
                "SELECT * FROM workflow_runs WHERE parent_run_id=%s", (parent["id"],)
            ).fetchall()
            self.assertEqual(len(children), 2)
            self.assertNotIn(parent["id"], {str(row["id"]) for row in STORE.candidates(connection)})
            for child in children:
                self.assertEqual(
                    child["config"]["runtime_binding"], parent["config"]["runtime_binding"]
                )
                self.assertEqual(
                    child["config"]["authorized_bindings"], parent["config"]["authorized_bindings"]
                )
                proposal = self.tally_result(parent, child["file_ids"][0])
                proposal["records"][0]["data"]["invoice_number"] = (
                    "BATCH-" + child["file_ids"][0][:8]
                )
                process(connection, child, executor=lambda *a, payload=proposal, **k: payload)
            # Child results never advance the shared parent task by themselves.
            self.assertEqual(
                connection.execute(
                    "SELECT state FROM workflow_runs WHERE id=%s", (parent["id"],)
                ).fetchone()["state"],
                "queued",
            )
        self.clear_policy()
        reconcile_once(URL)
        loaded = self.client.get(self.base + f"/runs/{parent['id']}").json()
        self.assertTrue(loaded["result"]["requires_review"])
        self.assertEqual(loaded["config"]["runtime_binding"]["policies"], policies)
        self.assertEqual(loaded["tally_writes"], [])
        self.assertEqual(loaded["state"], "review")
        with psycopg.connect(URL, row_factory=dict_row) as connection:
            from minkops_platform.accounts.tally_writes import prepare

            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE id=%s", (parent["id"],)
            ).fetchone()
            with self.assertRaisesRegex(ValueError, "explicit review"):
                prepare(connection, row, row["result"])
        approved = self.approve(loaded, loaded["result"])
        self.assertEqual(approved["state"], "writing")
        self.assertEqual(len(approved["tally_writes"]), 2)
        self.client.post(self.base + f"/runs/{parent['id']}/cancel-writes", headers=self.csrf)

    def test_tally_child_cannot_execute_changed_authorized_input(self):
        from unittest.mock import MagicMock

        discovery = self.tally_discovery()
        inputs = [self.upload_bill("first.pdf"), self.upload_bill("second.pdf")]
        parent, _ = self.launch(
            "bill-entry",
            file_ids=inputs,
            config={"output_mode": "tally_in_place", "discovery_id": discovery},
        )
        executor = MagicMock()
        with psycopg.connect(URL, row_factory=dict_row) as connection:
            child = connection.execute(
                "SELECT * FROM workflow_runs WHERE parent_run_id=%s LIMIT 1", (parent["id"],)
            ).fetchone()
            for grant in child["config"]["authorized_bindings"]:
                grant["sha256"] = "changed"
            with self.assertRaisesRegex(ValueError, "authorized resource snapshot"):
                process(connection, child, executor=executor)
        executor.assert_not_called()
