"""Definition installation is independent of demo fixtures and HTTP transport."""

import os
import unittest
from dataclasses import replace

import test_workflow_registration as registration
from jsonschema import ValidationError
from psycopg.types.json import Jsonb

from minkops_platform.installation import install, load_solution
from minkops_platform.resources import REPOSITORY_ROOT


class SolutionDefinitionTests(unittest.TestCase):
    def test_mock_solution_resolves_owned_workflows_and_employee_defaults(self):
        installation = load_solution(REPOSITORY_ROOT, "mock-client")
        self.assertEqual(installation.tenant_slug, "mock-tenant")
        self.assertEqual([e.metadata["key"] for e in installation.employees], ["accounts-desk"])
        self.assertEqual(set(installation.workflows), {"bill-entry", "statement-entry"})
        self.assertEqual(installation.workflows["bill-entry"].metadata["handler"], "desk.bill")
        self.assertEqual(installation.bindings["bill-entry"]["handler"], "desk.bill")
        # The demo workspace grants standing exception-only authorization; the
        # reusable definition keeps explicit review of every output by default.
        self.assertEqual(
            installation.bindings["bill-entry"]["defaults"]["review_mode"], "only_exceptions"
        )
        self.assertEqual(
            installation.workflows["bill-entry"].metadata["tenant_defaults"]["review_mode"],
            "all_outputs",
        )

    def test_path_escape_cannot_select_a_solution(self):
        with self.assertRaises(ValueError):
            load_solution(REPOSITORY_ROOT, "../employees")

    def test_pr_infra_enables_all_accounts_workflows_without_ledger_defaults(self):
        installation = load_solution(REPOSITORY_ROOT, "pr-infra")
        self.assertEqual([e.metadata['key'] for e in installation.employees], ['accounts-desk'])
        self.assertEqual(set(installation.workflows), {'statement-entry', 'bill-entry'})
        self.assertEqual(installation.bindings['bill-entry']['defaults']['review_mode'], 'all_outputs')
        self.assertNotIn('other_side_ledger',installation.workflows['statement-entry'].metadata['tenant_defaults'])
        self.assertEqual(installation.workflows['statement-entry'].session_bundle['model'], 'gpt-6-luna')
        self.assertEqual(installation.bindings['statement-entry']['handler'], 'desk.statement')
        # The client's own procedure is added to both workflows, and the rule it agreed is seeded into memory.
        for key in ('bill-entry', 'statement-entry'):
            self.assertIn('## Client procedure', installation.workflows[key].session_bundle['instructions'])
        self.assertEqual(installation.client, {'slug': 'pr-infra', 'name': 'PR Infra'})
        self.assertEqual([(r['key'], r['workflow']) for r in installation.rules['accounts-desk']],
                         [('neft-returns', 'statement-entry')])


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class InstallationDatabaseTests(unittest.TestCase):
    setUp = registration.WorkflowRegistrationTests.setUp
    remove_schema = registration.WorkflowRegistrationTests.remove_schema

    def composition(self):
        self.connection.execute("""INSERT INTO users(email,name,password_hash,email_verified_at,is_platform_admin)
            VALUES ('installer@example.com','Installer','unused',now(),true) ON CONFLICT DO NOTHING""")
        return replace(load_solution(REPOSITORY_ROOT, "mock-client"), tenant_slug="mock")

    def test_a_clients_business_is_created_and_its_agreed_rules_seeded_once(self):
        self.composition()
        composition = replace(load_solution(REPOSITORY_ROOT, "pr-infra"), tenant_slug="mock")
        for _ in range(2):
            install(self.connection, composition, actor_email="installer@example.com")
        client = self.connection.execute(
            "SELECT id, name FROM client_businesses WHERE tenant_id=%s AND slug='pr-infra'", (self.tenant,)).fetchone()
        self.assertEqual(client[1], "PR Infra")
        rules = self.connection.execute(
            "SELECT workflow_key, status FROM memory_instructions WHERE client_id=%s", (client[0],)).fetchall()
        self.assertEqual(rules, [("statement-entry", "active")])

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
