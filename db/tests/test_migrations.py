"""Integration checks for the clean OLTP baseline.

Run against a disposable PostgreSQL database with TEST_DATABASE_URL set.
"""

import importlib.util
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("TEST_DATABASE_URL")
spec = importlib.util.spec_from_file_location("runner", ROOT / "db/migrate.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@contextmanager
def database_before(version):
    """A fresh database migrated up to, not including, `version`, for a migration's own upgrade test."""
    name = "minkops_migration_" + uuid4().hex
    with psycopg.connect(make_conninfo(URL, dbname="postgres"), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            url = make_conninfo(URL, dbname=name)
            with psycopg.connect(url) as connection:
                connection.execute("""CREATE TABLE schema_migrations (version text PRIMARY KEY, checksum text NOT NULL,
                                      applied_at timestamptz NOT NULL DEFAULT now())""")
                for earlier, (source, checksum) in runner.sources(runner.MIGRATIONS).items():
                    if earlier < version:
                        runner.apply(connection, earlier, source, checksum)
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class MigrationTests(unittest.TestCase):
    def test_client_profiles_allow_one_live_version_per_scope(self):
        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            tenant = connection.execute("INSERT INTO tenants(slug,name) VALUES (%s,'Profiles') RETURNING id",
                                        ("profiles-" + uuid4().hex,)).fetchone()[0]
            insert = """INSERT INTO client_profiles(tenant_id,kind,scope_key,version,status,payload)
                VALUES (%s,'posting_profile','company',%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id"""
            self.assertIsNotNone(connection.execute(insert, (tenant, 1, "deriving", None)).fetchone())
            self.assertIsNone(connection.execute(insert, (tenant, 2, "deriving", None)).fetchone())
            connection.execute("UPDATE client_profiles SET status='failed' WHERE tenant_id=%s", (tenant,))
            self.assertIsNotNone(connection.execute(insert, (tenant, 2, "deriving", None)).fetchone())
            with self.assertRaises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(insert, (tenant, 3, "superseded", None))
                connection.execute("UPDATE client_profiles SET status='active' WHERE tenant_id=%s AND version=3", (tenant,))

    def test_retired_discovery_preference_is_removed_without_changing_other_settings(self):
        from psycopg.types.json import Jsonb

        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            tenant = connection.execute(
                "INSERT INTO tenants(slug,name) VALUES (%s,'Migration test') RETURNING id",
                ("discovery-migration-" + uuid4().hex,),
            ).fetchone()[0]
            for key, presentation in [
                ("source-discovery", "accounts-discovery"),
                ("client-discovery", "accounts-discovery"),
                ("another-workflow", "proposal"),
            ]:
                connection.execute(
                    "INSERT INTO workflows(tenant_id,key,name,description,config_schema,config_values,execution_binding) VALUES (%s,%s,'Test','Test',%s,%s,%s)",
                    (
                        tenant,
                        key,
                        Jsonb(
                            {
                                "properties": {
                                    "discovery_depth": {"type": "string"},
                                    "max_files": {"type": "integer"},
                                },
                                "required": ["discovery_depth", "max_files"],
                            }
                        ),
                        Jsonb({"discovery_depth": "structure", "max_files": 57}),
                        Jsonb({"presentation": presentation}),
                    ),
                )
            migration = (ROOT / "db/migrations/0003_complete_source_discovery.sql").read_text()
            for _ in range(2):
                connection.execute(migration)
            rows = connection.execute(
                "SELECT key,config_values,config_schema,config_version FROM workflows WHERE tenant_id=%s",
                (tenant,),
            ).fetchall()
            for key, values, schema, version in rows:
                if key == "another-workflow":
                    self.assertEqual(values["discovery_depth"], "structure")
                    self.assertEqual(version, 1)
                else:
                    self.assertEqual(values, {"max_files": 57})
                    self.assertNotIn("discovery_depth", schema["properties"])
                    self.assertEqual(schema["required"], ["max_files"])
                    self.assertEqual(version, 2)

    def test_retired_bill_output_mode_is_removed_without_changing_other_settings(self):
        from psycopg.types.json import Jsonb

        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            tenant = connection.execute(
                "INSERT INTO tenants(slug,name) VALUES (%s,'Migration test') RETURNING id",
                ("bill-migration-" + uuid4().hex,),
            ).fetchone()[0]
            schema = {"properties": {"review_mode": {"type": "string"},
                                     "output_mode": {"enum": ["excel_in_place", "tally_in_place"],
                                                     "x-enabled-options": ["tally_in_place"]}},
                      "required": ["review_mode", "output_mode"]}
            for key in ("bill-entry", "another-workflow"):
                connection.execute(
                    "INSERT INTO workflows(tenant_id,key,name,description,config_schema,config_values,execution_binding) VALUES (%s,%s,'Test','Test',%s,%s,%s)",
                    (tenant, key, Jsonb(schema), Jsonb({"review_mode": "all_outputs", "output_mode": "excel_in_place"}),
                     Jsonb({"presentation": "accounts-bill"})),
                )
            migration = (ROOT / "db/migrations/0018_retire_excel_bill_destination.sql").read_text()
            for _ in range(2):
                connection.execute(migration)
            rows = {key: (values, migrated, version) for key, values, migrated, version in connection.execute(
                "SELECT key,config_values,config_schema,config_version FROM workflows WHERE tenant_id=%s", (tenant,))}
            values, migrated, version = rows["bill-entry"]
            self.assertEqual(values, {"review_mode": "all_outputs"})
            self.assertEqual((list(migrated["properties"]), migrated["required"], version), (["review_mode"], ["review_mode"], 2))
            self.assertEqual((rows["another-workflow"][0]["output_mode"], rows["another-workflow"][2]), ("excel_in_place", 1))

    def test_desktop_binding_and_dispatch_foreign_keys_prevent_cross_tenant_links(self):
        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            prefix = "desktop-migration-" + uuid4().hex
            first = connection.execute(
                "INSERT INTO tenants(slug,name) VALUES (%s,'A') RETURNING id", (prefix + "-a",)
            ).fetchone()[0]
            second = connection.execute(
                "INSERT INTO tenants(slug,name) VALUES (%s,'B') RETURNING id", (prefix + "-b",)
            ).fetchone()[0]
            owner = connection.execute(
                "INSERT INTO users(email,name,password_hash) VALUES (%s,'Owner','test-only') RETURNING id",
                (prefix + "@example.com",),
            ).fetchone()[0]
            device = connection.execute(
                "INSERT INTO desktop_devices(tenant_id,owner_id,installation_id,name,token_hash) VALUES (%s,%s,%s,'PC',%s) RETURNING id",
                (first, owner, uuid4(), prefix),
            ).fetchone()[0]
            source = connection.execute(
                "INSERT INTO account_sources(tenant_id,actor_id,label,writable) VALUES (%s,%s,'Folder',true) RETURNING id",
                (second, owner),
            ).fetchone()[0]
            task = connection.execute(
                "INSERT INTO tasks(tenant_id,title) VALUES (%s,'Task') RETURNING id", (second,)
            ).fetchone()[0]
            with self.assertRaises(psycopg.errors.ForeignKeyViolation), connection.transaction():
                connection.execute(
                    "INSERT INTO desktop_source_bindings(tenant_id,device_id,source_id) VALUES (%s,%s,%s)",
                    (first, device, source),
                )
            with self.assertRaises(psycopg.errors.ForeignKeyViolation), connection.transaction():
                connection.execute(
                    "INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,request_key,request_hash) VALUES (%s,%s,%s,%s,'tally.probe',%s,'test-only')",
                    (first, device, owner, task, uuid4()),
                )

    def test_baseline_is_repeatable_and_scoped(self):
        for _ in range(2):
            subprocess.run(
                [sys.executable, str(ROOT / "db" / "migrate.py")],
                cwd=ROOT,
                env={**os.environ, "DATABASE_URL": URL},
                check=True,
            )

        with psycopg.connect(URL) as connection:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            self.assertTrue(
                {
                    "tenants",
                    "users",
                    "memberships",
                    "employees",
                    "workflows",
                    "workflow_employees",
                    "tasks",
                    "task_events",
                    "event_outbox",
                    "schema_migrations",
                }
                <= names
            )
            self.assertFalse({"agent_state", "agent_intercom_queue", "tickets"} & names)
            self.assertTrue({"desktop_devices", "desktop_jobs", "desktop_source_bindings"} <= names)
            self.assertEqual(
                connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0],
                len(list((ROOT / "db" / "migrations").glob("*.sql"))),
            )

    def test_cross_tenant_workflow_employee_link_is_rejected(self):
        subprocess.run(
            [sys.executable, str(ROOT / "db" / "migrate.py")],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": URL},
            check=True,
        )
        with psycopg.connect(URL) as connection:
            with connection.transaction():
                first = connection.execute(
                    "INSERT INTO tenants (slug, name) VALUES ('migration-a', 'A') RETURNING id"
                ).fetchone()[0]
                second = connection.execute(
                    "INSERT INTO tenants (slug, name) VALUES ('migration-b', 'B') RETURNING id"
                ).fetchone()[0]
                employee = connection.execute(
                    "INSERT INTO employees (tenant_id, key, name) VALUES (%s, 'one', 'One') RETURNING id",
                    (first,),
                ).fetchone()[0]
                workflow = connection.execute(
                    "INSERT INTO workflows (tenant_id, key, name) VALUES (%s, 'two', 'Two') RETURNING id",
                    (second,),
                ).fetchone()[0]
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    "INSERT INTO workflow_employees (tenant_id, workflow_id, employee_id) VALUES (%s, %s, %s)",
                    (first, workflow, employee),
                )
            connection.rollback()
            connection.execute("DELETE FROM tenants WHERE id IN (%s, %s)", (first, second))

    def test_unknown_changed_or_parked_history_is_refused_and_changes_nothing(self):
        """A database whose history this checkout does not know, has changed, or predates the baseline (the parked
        build's) is refused before anything runs."""
        baseline = (runner.BASELINE, runner.sources(runner.MIGRATIONS)[runner.BASELINE][1])
        for history, expected in [([baseline, ("9999_unknown_future", "hash")], "Unknown migration history"),
                                  ([(runner.BASELINE, "changed")], "Applied migration changed"),
                                  ([("0002_accounts_runs", "archived")], "predates the baseline")]:
            schema = "history_" + uuid4().hex
            scoped = make_conninfo(URL, options=f"-csearch_path={schema},public")
            with psycopg.connect(URL, autocommit=True) as c:
                c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                with psycopg.connect(scoped) as c:
                    c.execute("CREATE TABLE schema_migrations(version text PRIMARY KEY, checksum text, "
                              "applied_at timestamptz DEFAULT now())")
                    for version, checksum in history:
                        c.execute("INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)", (version, checksum))
                with self.assertRaisesRegex(RuntimeError, expected):
                    runner.migrate(scoped)
                with psycopg.connect(scoped) as c:
                    self.assertEqual(c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall(),
                                     sorted((version,) for version, _ in history))
                    self.assertIsNone(c.execute("SELECT to_regclass(%s)", (schema + ".tenants",)).fetchone()[0])
            finally:
                with psycopg.connect(URL, autocommit=True) as c:
                    c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

    def test_a_database_holding_the_parked_builds_work_refuses_its_retirement(self):
        """Migration 0032 drops the old build's tables only where they are empty, never its history."""
        retirement = (ROOT / "db/migrations/0032_drop_legacy_runtime.sql").read_text()
        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            connection.execute("CREATE TEMP TABLE workflow_runs (id int) ON COMMIT DROP")
            connection.execute("INSERT INTO workflow_runs VALUES (1)")
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "parked build's work"):
                connection.execute(retirement)

    def test_supplier_jobs_become_ledger_jobs_and_a_pending_supplier_creation_holds_the_upgrade(self):
        """Migration 0037 renames the supplier jobs a database already holds, and waits for any pending creation."""
        upgrade = (ROOT / "db/migrations/0037_ledger_writes.sql").read_text()
        # The older constraint, not validated against jobs other tests left in this database.
        older = """ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
            ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK (operation = ANY (ARRAY[
            'tally.probe','files.refresh','tally.sync','tally.write','tally.supplier'])) NOT VALID"""
        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            tenant = connection.execute("INSERT INTO tenants(slug,name) VALUES (%s,'Ledgers') RETURNING id",
                                        ("ledgers-" + uuid4().hex,)).fetchone()[0]
            user = connection.execute("INSERT INTO users(email,name,password_hash) VALUES (%s,'U','x') RETURNING id",
                                      (uuid4().hex + "@example.com",)).fetchone()[0]
            device = connection.execute(
                """INSERT INTO desktop_devices(tenant_id,owner_id,installation_id,name,token_hash)
                   VALUES (%s,%s,%s,'PC',%s) RETURNING id""", (tenant, user, uuid4(), uuid4().hex)).fetchone()[0]
            task = connection.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Create') RETURNING id",
                                      (tenant,)).fetchone()[0]
            connection.execute(older)
            connection.execute(
                """INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,state,request_key,request_hash)
                   VALUES (%s,%s,%s,%s,'tally.supplier','{}','completed',%s,'h')""", (tenant, device, user, task, uuid4()))
            connection.execute(upgrade)
            self.assertEqual(connection.execute("SELECT operation FROM desktop_jobs WHERE tenant_id=%s",
                                                (tenant,)).fetchone()[0], "tally.ledger")
            with self.assertRaises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute("UPDATE desktop_jobs SET operation='tally.supplier' WHERE tenant_id=%s", (tenant,))
            # A supplier creation still pending (a temporary table shadows the real one) holds the upgrade.
            connection.execute("CREATE TEMP TABLE native_writes (plan jsonb, finished_at timestamptz) ON COMMIT DROP")
            connection.execute("""INSERT INTO native_writes VALUES ('{"kind": "supplier"}', NULL)""")
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "supplier creation is still pending"):
                connection.execute(upgrade)

    def test_people_belong_to_one_workspace_and_members_keep_the_workflows_they_ran(self):
        """Migration 0040: a person in two workspaces holds the upgrade. Members keep every workflow they could run,
        admins need none, and an open practice question names the workflow its answer changes."""
        upgrade = (ROOT / "db/migrations/0040_people.sql").read_text()
        with database_before("0040_people") as url, psycopg.connect(url) as c:
            tenant, other = (c.execute("INSERT INTO tenants(slug,name) VALUES (%s,%s) RETURNING id",
                                       (f"t-{uuid4().hex[:8]}", "Tenant")).fetchone()[0] for _ in range(2))
            admin, member = (c.execute("""INSERT INTO users(email,name,password_hash,email_verified_at)
                                         VALUES (%s,'U','x',now()) RETURNING id""",
                                       (f"{uuid4().hex}@example.com",)).fetchone()[0] for _ in range(2))
            c.execute("INSERT INTO memberships(tenant_id,user_id,role) VALUES (%s,%s,'admin'),(%s,%s,'member'),"
                      "(%s,%s,'member')", (tenant, admin, tenant, member, other, member))
            c.execute("INSERT INTO employees(tenant_id,key,name) VALUES (%s,'accounts-desk','Desk')", (tenant,))
            flows = {key: c.execute("INSERT INTO workflows(tenant_id,key,name,description) VALUES (%s,%s,%s,'') "
                                    "RETURNING id", (tenant, key, key)).fetchone()[0]
                     for key in ("bill-entry", "statement-entry")}
            client = c.execute("INSERT INTO client_businesses(tenant_id,slug,name) VALUES (%s,'c','C') RETURNING id",
                               (tenant,)).fetchone()[0]
            device = c.execute("""INSERT INTO desktop_devices(tenant_id,owner_id,installation_id,name,token_hash)
                                  VALUES (%s,%s,%s,'PC',%s) RETURNING id""",
                               (tenant, admin, uuid4(), uuid4().hex)).fetchone()[0]
            company = c.execute("""INSERT INTO companies(tenant_id,client_id,device_id,guid,books_from,name,status)
                                   VALUES (%s,%s,%s,'g','2026-04-01','Co','authorised') RETURNING id""",
                                (tenant, client, device)).fetchone()[0]
            task = c.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Sync') RETURNING id", (tenant,)).fetchone()[0]
            items = {}
            for probe in ("bank_payments", "discounts"):
                question = c.execute(
                    """INSERT INTO practice_questions(tenant_id,client_id,company_id,employee_key,probe,prompt,options)
                       VALUES (%s,%s,%s,'accounts-desk',%s,'?','[]') RETURNING id""",
                    (tenant, client, company, probe)).fetchone()[0]
                items[probe] = c.execute(
                    """INSERT INTO attention_items(tenant_id,task_id,event_key,identifier,label,kind,target)
                       VALUES (%s,%s,%s,'Co','Practice question','practice',%s) RETURNING id""",
                    (tenant, task, f"practice:{question}", f'{{"question_id": "{question}"}}')).fetchone()[0]
            c.commit()
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "belongs to several workspaces"):
                c.execute(upgrade)
            c.rollback()
            c.execute("DELETE FROM memberships WHERE tenant_id=%s", (other,))
            c.execute(upgrade)
            assigned = c.execute("SELECT user_id, workflow_id FROM workflow_assignments WHERE tenant_id=%s",
                                 (tenant,)).fetchall()
            self.assertEqual(sorted(assigned), sorted((member, flow) for flow in flows.values()))
            routed = dict(c.execute("SELECT id, target->'workflows' FROM attention_items WHERE tenant_id=%s",
                                    (tenant,)).fetchall())
            self.assertEqual(routed, {items["bank_payments"]: ["statement-entry"], items["discounts"]: ["bill-entry"]})
            with self.assertRaises(psycopg.errors.UniqueViolation), c.transaction():
                c.execute("INSERT INTO memberships(tenant_id,user_id,role) VALUES (%s,%s,'member')", (other, admin))


if __name__ == "__main__":
    unittest.main()
