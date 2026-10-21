"""Integration checks for the clean OLTP baseline.

Run against a disposable PostgreSQL database with TEST_DATABASE_URL set.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("TEST_DATABASE_URL")


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

    def test_unfinished_work_on_retired_contracts_is_stopped_and_left_in_attention(self):
        from psycopg.types.json import Jsonb

        with psycopg.connect(URL) as connection, connection.transaction(force_rollback=True):
            sql = connection.execute
            tenant = sql("INSERT INTO tenants(slug,name) VALUES (%s,'Drain') RETURNING id", ("drain-" + uuid4().hex,)).fetchone()[0]
            user = sql("INSERT INTO users(email,name,password_hash) VALUES (%s,'Operator','x') RETURNING id",
                       (uuid4().hex + "@example.test",)).fetchone()[0]
            device = sql("INSERT INTO desktop_devices(tenant_id,owner_id,installation_id,name,token_hash) VALUES (%s,%s,%s,'PC',%s) RETURNING id",
                         (tenant, user, uuid4(), uuid4().hex)).fetchone()[0]
            for key in ("bill-entry", "statement-entry", "source-discovery"):
                sql("INSERT INTO workflows(tenant_id,key,name,description,config_schema,config_values,execution_binding) VALUES (%s,%s,'W','W','{}','{}','{}')",
                    (tenant, key))

            def run(key, config, *, state="review", result=None):
                task = sql("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Task') RETURNING id", (tenant,)).fetchone()[0]
                return sql("""INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,definition_version,request_key,
                    request_hash,config,file_ids,state,result) VALUES (%s,%s,%s,%s,'0.1.0',%s,'h',%s,'[]',%s,%s) RETURNING id,task_id""",
                           (tenant, task, user, key, uuid4(), Jsonb(config), state, Jsonb(result) if result else None)).fetchone()

            bound = {"runtime_binding": {"handler": "accounts.bill", "presentation": "accounts-bill"}}
            proposals = run("bill-entry", {**bound, "tally_target": {"companies": [], "voucher_proposal_version": 1}})
            fixed = run("bill-entry", {**bound, "tally_target": {"company": "Test", "port": 9000}}, state="writing")
            excel = run("bill-entry", {"catalog_snapshot": {"sheets": []}})
            older_rows = run("statement-entry", {}, result={"records": [{"status": "ready", "plan": {"format_version": 4}}]})
            v5_rows = run("statement-entry", {}, result={"records": [{"status": "ready", "plan": {"format_version": 5}},
                                                                      {"status": "saved", "plan": {"format_version": 4}}]})
            history = run("source-discovery", {}, state="completed")
            write = sql("""INSERT INTO account_tally_writes(tenant_id,run_id,device_id,company,identity,record_index,plan,destination_key)
                VALUES (%s,%s,%s,'Test','i',0,'{"format_version":3}','company:x') RETURNING id""", (tenant, fixed[0], device)).fetchone()[0]
            job = sql("""INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
                VALUES (%s,%s,%s,%s,'tally.save',%s,%s,'h') RETURNING id""",
                      (tenant, device, user, fixed[1], Jsonb({"run_id": str(fixed[0]), "write_id": str(write)}), uuid4())).fetchone()[0]
            migration = (ROOT / "db/migrations/0019_retire_legacy_runs.sql").read_text()
            for _ in range(2):
                sql(migration)

            def state(row):
                return sql("""SELECT r.state, t.control_state, r.error FROM workflow_runs r JOIN tasks t ON t.id=r.task_id
                    WHERE r.id=%s""", (row[0],)).fetchone()

            for row in (proposals, v5_rows):
                self.assertEqual(state(row)[:2], ("review", "active"))
            retired = (fixed, excel, older_rows)
            for row in retired:
                self.assertEqual(state(row)[:2], ("failed", "stopped"))
                self.assertIn("Start a new run", state(row)[2])
            self.assertIsNotNone(sql("SELECT cancelled_at FROM account_tally_writes WHERE id=%s", (write,)).fetchone()[0])
            self.assertEqual(sql("SELECT state FROM desktop_jobs WHERE id=%s", (job,)).fetchone()[0], "failed")
            items = sql("SELECT event_key,label,status FROM attention_items WHERE tenant_id=%s ORDER BY event_key", (tenant,)).fetchall()
            self.assertEqual(items, sorted((f"retired:{row[0]}", "Run retired", "pending") for row in retired))
            self.assertEqual(sql("SELECT count(*) FROM attention_events e JOIN attention_items a ON a.id=e.item_id WHERE a.tenant_id=%s",
                                 (tenant,)).fetchone()[0], 3)
            self.assertEqual(sql("SELECT config->'runtime_binding' FROM workflow_runs WHERE id=%s", (history[0],)).fetchone()[0],
                             {"handler": "accounts.discovery", "presentation": "accounts-discovery"})
            self.assertEqual(sql("SELECT config->'runtime_binding' FROM workflow_runs WHERE id=%s", (excel[0],)).fetchone()[0],
                             {"handler": "accounts.bill", "presentation": "accounts-bill"})

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


if __name__ == "__main__":
    unittest.main()
