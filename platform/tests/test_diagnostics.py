"""Internal diagnostics survive failures without copying provider payloads."""

import os
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg
from jsonschema import ValidationError
from psycopg.rows import dict_row


class DiagnosticErrorTests(TestCase):
    def test_schema_error_identifies_path_and_rule_without_dumping_instance(self):
        from minkops_platform.runtime.diagnostics import error_details

        error = ValidationError(
            "secret instance", path=["records", 0, "evidence"], validator="enum"
        )
        details = error_details(error)
        self.assertEqual(details["path"], ["records", 0, "evidence"])
        self.assertEqual(details["validator"], "enum")
        self.assertNotIn("secret", str(details))

    def test_provider_errors_do_not_copy_secrets_or_request_bodies(self):
        from minkops_platform.runtime.diagnostics import error_details

        self.assertNotIn("secret", str(error_details(RuntimeError("secret credential"))))

    def test_stage_failure_is_recorded_before_propagating(self):
        from minkops_platform.runtime.diagnostics import stage

        connection, run = MagicMock(), {"tenant_id": uuid4(), "id": uuid4()}
        with patch("minkops_platform.runtime.diagnostics.record") as record:
            with (
                self.assertRaises(RuntimeError),
                stage(connection, run, "prepare", "Prepare authorized inputs"),
            ):
                raise RuntimeError("secret credential")
            args = record.call_args
            self.assertEqual(args.args[2], "prepare.failed")
            self.assertNotIn("secret", str(args))


@skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class DiagnosticPersistenceTests(TestCase):
    def test_diagnostic_commits_independently_and_enforces_tenant_run_identity(self):
        from minkops_platform.runtime.diagnostics import record

        url = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(url, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "SELECT id FROM tenants WHERE slug='mock-tenant'"
            ).fetchone()["id"]
            actor = connection.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
            task = connection.execute(
                "INSERT INTO tasks(tenant_id,title) VALUES(%s,'Diagnostics') RETURNING id",
                (tenant,),
            ).fetchone()["id"]
            run = connection.execute(
                """INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
                definition_version,request_key,request_hash,config,file_ids)
                VALUES(%s,%s,%s,'bill-entry','0.9.0',%s,'diagnostics','{}','[]') RETURNING *""",
                (tenant, task, actor, uuid4()),
            ).fetchone()
            connection.commit()
            record(
                connection,
                run,
                "validation.failed",
                "Output violates evidence contract",
                level="error",
                details={"path": ["records", 0]},
            )
            connection.rollback()
            row = connection.execute(
                "SELECT * FROM workflow_run_diagnostics WHERE run_id=%s", (run["id"],)
            ).fetchone()
            self.assertEqual(row["summary"], "Output violates evidence contract")
            self.assertEqual(row["details"]["path"], ["records", 0])
            record(connection, {**run, "tenant_id": uuid4()}, "test", "Wrong tenant")
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM workflow_run_diagnostics WHERE run_id=%s", (run["id"],)
                ).fetchone()["count"],
                1,
            )
