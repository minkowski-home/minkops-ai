"""Definition installation is independent of demo fixtures and HTTP transport."""

import os
import unittest
from dataclasses import replace

import test_workflow_registration as registration
from jsonschema import ValidationError
from minkops_platform.installation import install, load_solution
from minkops_platform.resources import REPOSITORY_ROOT
from psycopg.types.json import Jsonb


class SolutionDefinitionTests(unittest.TestCase):
    def test_mock_solution_resolves_owned_workflows_and_employee_defaults(self):
        installation = load_solution(REPOSITORY_ROOT, "mock-client")
        self.assertEqual(installation.tenant_slug, "mock-tenant")
        self.assertEqual([e.metadata["key"] for e in installation.employees], ["accounts-desk"])
        self.assertEqual(set(installation.workflows), {"source-discovery", "bill-entry"})
        self.assertEqual(installation.workflows["bill-entry"].metadata["handler"], "accounts.bill")
        self.assertEqual(
            installation.workflows["bill-entry"].tenant_schema["properties"]["output_mode"][
                "x-enabled-options"
            ],
            ["tally_in_place"],
        )
        self.assertEqual(
            installation.bindings["bill-entry"]["defaults"]["output_mode"], "tally_in_place"
        )

    def test_path_escape_cannot_select_a_solution(self):
        with self.assertRaises(ValueError):
            load_solution(REPOSITORY_ROOT, "../employees")

    def test_empty_client_does_not_install_demo_employees(self):
        installation = load_solution(REPOSITORY_ROOT, "pr-infra")
        self.assertEqual(installation.employees, [])
        self.assertEqual(installation.workflows, {})


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class InstallationDatabaseTests(unittest.TestCase):
    setUp = registration.WorkflowRegistrationTests.setUp
    remove_schema = registration.WorkflowRegistrationTests.remove_schema

    def composition(self):
        self.connection.execute("""INSERT INTO users(email,name,password_hash,email_verified_at,is_platform_admin)
            VALUES ('installer@example.com','Installer','unused',now(),true) ON CONFLICT DO NOTHING""")
        return replace(load_solution(REPOSITORY_ROOT, "mock-client"), tenant_slug="mock")

    def test_repeat_install_preserves_employee_and_workflow_settings_and_status(self):
        composition = self.composition()
        install(self.connection, composition, actor_email="installer@example.com")
        self.connection.execute(
            "UPDATE employees SET status='inactive',config_values=%s WHERE tenant_id=%s",
            (Jsonb({"daily_digest": True}), self.tenant),
        )
        self.connection.execute(
            "UPDATE workflows SET status='paused' WHERE tenant_id=%s", (self.tenant,)
        )
        install(self.connection, composition, actor_email="installer@example.com")
        self.assertEqual(
            self.connection.execute(
                "SELECT status,config_values FROM employees WHERE tenant_id=%s", (self.tenant,)
            ).fetchone(),
            ("inactive", {"daily_digest": True}),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT DISTINCT status FROM workflows WHERE tenant_id=%s", (self.tenant,)
            ).fetchall(),
            [("paused",)],
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT count(*) FROM workflows WHERE tenant_id=%s", (self.other,)
            ).fetchone()[0],
            0,
        )

    def test_incompatible_employee_settings_roll_back_the_entire_install(self):
        composition = self.composition()
        self.connection.execute(
            "UPDATE employees SET config_values=%s WHERE tenant_id=%s",
            (Jsonb({"unknown": True}), self.tenant),
        )
        with self.assertRaises(ValidationError):
            install(self.connection, composition, actor_email="installer@example.com")
        self.assertEqual(self.connection.execute("SELECT count(*) FROM workflows").fetchone()[0], 0)

    def test_members_cannot_install_or_grant_themselves_privileges(self):
        from minkops_platform.errors import ServiceError

        composition = self.composition()
        self.connection.execute("UPDATE users SET is_platform_admin=false")
        with self.assertRaises(ServiceError):
            install(self.connection, composition, actor_email="installer@example.com")

    def test_dry_run_really_rolls_back_registration(self):
        composition = self.composition()
        with self.connection.transaction(force_rollback=True):
            install(self.connection, composition, actor_email="installer@example.com")
            self.assertEqual(
                self.connection.execute("SELECT count(*) FROM workflows").fetchone()[0], 2
            )
        self.assertEqual(self.connection.execute("SELECT count(*) FROM workflows").fetchone()[0], 0)
