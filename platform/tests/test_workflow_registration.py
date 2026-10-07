"""Registration checks in an isolated schema on TEST_DATABASE_URL."""

import os
import unittest
import uuid
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import psycopg
from jsonschema import ValidationError
from minkops_platform.workflows import load_definition, register_workflow
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class WorkflowRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(URL)
        self.addCleanup(self.connection.close)
        self.schema_name = "step2_" + uuid.uuid4().hex
        self.connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema_name))
        )
        self.connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema_name))
        )
        for migration in sorted((ROOT / "db/migrations").glob("*.sql")):
            self.connection.execute(migration.read_text())
        self.connection.commit()
        self.addCleanup(self.remove_schema)
        self.tenant = self.connection.execute(
            "INSERT INTO tenants (slug, name) VALUES ('mock', 'Mock') RETURNING id",
        ).fetchone()[0]
        self.other = self.connection.execute(
            "INSERT INTO tenants (slug, name) VALUES ('other', 'Other') RETURNING id",
        ).fetchone()[0]
        for tenant in (self.tenant, self.other):
            self.connection.execute(
                "INSERT INTO employees (tenant_id, key, name) VALUES (%s, 'accounts-desk', 'Accounts desk')",
                (tenant,),
            )
        self.definition = load_definition(ROOT / "employees/accounts-desk/workflows/bill-entry")

    def remove_schema(self):
        self.connection.rollback()
        self.connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema_name))
        )
        self.connection.commit()

    def test_repeat_registration_preserves_settings_status_and_links(self):
        first = register_workflow(self.connection, self.tenant, self.definition)
        settings = {"review_mode": "only_exceptions", "output_mode": "draft_excel"}
        self.connection.execute(
            "UPDATE workflows SET config_values = %s, status = 'paused' WHERE id = %s",
            (Jsonb(settings), first),
        )
        second = register_workflow(self.connection, self.tenant, self.definition)
        self.assertEqual(first, second)
        self.assertEqual(
            self.connection.execute(
                "SELECT config_values, status, config_version FROM workflows WHERE id = %s",
                (first,),
            ).fetchone(),
            (settings, "paused", 1),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT count(*) FROM workflow_employees WHERE workflow_id = %s",
                (first,),
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT count(*) FROM workflows WHERE tenant_id = %s",
                (self.other,),
            ).fetchone()[0],
            0,
        )

    def test_incompatible_update_does_not_replace_settings(self):
        workflow_id = register_workflow(self.connection, self.tenant, self.definition)
        restricted = deepcopy(self.definition.tenant_schema)
        restricted["properties"]["review_mode"]["enum"] = ["only_exceptions"]
        with self.assertRaises(ValidationError):
            register_workflow(
                self.connection,
                self.tenant,
                replace(self.definition, tenant_schema=restricted),
                {"review_mode": "only_exceptions", "output_mode": "draft_excel"},
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT config_values ->> 'review_mode', config_version FROM workflows WHERE id = %s",
                (workflow_id,),
            ).fetchone(),
            ("all_outputs", 1),
        )

    def test_same_definition_can_be_installed_for_another_tenant(self):
        first = register_workflow(self.connection, self.tenant, self.definition)
        second = register_workflow(self.connection, self.other, self.definition)
        self.assertNotEqual(first, second)
        rows = self.connection.execute(
            """SELECT w.tenant_id = e.tenant_id FROM workflow_employees link
               JOIN workflows w ON w.id = link.workflow_id
               JOIN employees e ON e.id = link.employee_id""",
        ).fetchall()
        self.assertEqual(rows, [(True,), (True,)])

    def test_compatible_schema_update_increments_version_once(self):
        workflow_id = register_workflow(self.connection, self.tenant, self.definition)
        updated_schema = deepcopy(self.definition.tenant_schema)
        updated_schema["properties"]["review_mode"]["description"] = "Default review preference"
        updated = replace(self.definition, tenant_schema=updated_schema)
        register_workflow(self.connection, self.tenant, updated)
        register_workflow(self.connection, self.tenant, updated)
        self.assertEqual(
            self.connection.execute(
                "SELECT config_version FROM workflows WHERE id = %s",
                (workflow_id,),
            ).fetchone()[0],
            2,
        )


if __name__ == "__main__":
    unittest.main()
