"""Converge either released branch schema without rewriting applied migrations."""

import hashlib
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]
URL = os.getenv("TEST_DATABASE_URL")
spec = importlib.util.spec_from_file_location("upgrade_migrations", ROOT / "db/migrate.py")
migrations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrations)


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class BranchUpgradeTests(unittest.TestCase):
    def test_fresh_and_both_branch_upgrades_preserve_runs_checksums_and_view_writes(self):
        for branch in (None, "platform-ai/workflow-architecture", "employees/bill-entry"):
            with self.subTest(branch=branch):
                self.check_upgrade(branch)

    def check_upgrade(self, branch):
        schema = "upgrade_" + uuid4().hex
        scoped = make_conninfo(URL, options=f"-csearch_path={schema},public")
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            with psycopg.connect(scoped) as connection:
                connection.execute(
                    "CREATE TABLE schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz DEFAULT now())"
                )
                if branch:
                    directory = ROOT / "db/migrations"
                    names = sorted(
                        path
                        for path in directory.glob("*.sql")
                        if path.name <= "0008_source_discovery.sql"
                    )
                    retained = {
                        "0009_workflow_bindings.sql": "522443cfe3279c94d0f50fd956d1124eb9a4bc18958b6197a4a03923aacfb0be",
                        "0009_bill_entry.sql": "3e68bc3bcc30d60385e126e8520a6c586f50d58fcb082f061c372c8a6a2e2dce",
                        "0010_bill_company_reservation.sql": "9e5d2e4378cdd2ce6aa42cf8dbee45101521307ab30252f50179eb5f7e243e50",
                    }
                    suffix = (
                        ["0009_workflow_bindings.sql"]
                        if branch == "platform-ai/workflow-architecture"
                        else ["0009_bill_entry.sql", "0010_bill_company_reservation.sql"]
                    )
                    names.extend(directory / name for name in suffix)
                    for name in names:
                        source = name.read_bytes()
                        if name.name in retained:
                            # Original released migrations are immutable. These
                            # fixtures also work after branch retirement/shallow clone.
                            self.assertEqual(
                                hashlib.sha256(source).hexdigest(), retained[name.name]
                            )
                        connection.execute(source.decode())
                        connection.execute(
                            "INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)",
                            (Path(name).stem, hashlib.sha256(source).hexdigest()),
                        )
                    tenant = connection.execute(
                        "INSERT INTO tenants(slug,name) VALUES ('history','History') RETURNING id"
                    ).fetchone()[0]
                    actor = connection.execute(
                        "INSERT INTO users(email,name,password_hash) VALUES ('history@example.com','Owner','test') RETURNING id"
                    ).fetchone()[0]
                    workflow = connection.execute(
                        "INSERT INTO workflows(tenant_id,key,name,status) VALUES (%s,'bill-entry','Bill entry','paused') RETURNING id",
                        (tenant,),
                    ).fetchone()[0]
                    task = connection.execute(
                        "INSERT INTO tasks(tenant_id,workflow_id,title) VALUES (%s,%s,'Historical approval') RETURNING id",
                        (tenant, workflow),
                    ).fetchone()[0]
                    run = connection.execute(
                        """INSERT INTO account_runs(tenant_id,task_id,actor_id,workflow_key,definition_version,request_key,request_hash,config,file_ids,state,session_id,turn_id,result)
                        VALUES (%s,%s,%s,'bill-entry','0.6.0',%s,'original','{"review_mode":"all_outputs"}','[]','review','paid-session','paid-turn','{"records":[]}') RETURNING *""",
                        (tenant, task, actor, uuid4()),
                    ).fetchone()
                    before = connection.execute(
                        "SELECT version,checksum FROM schema_migrations ORDER BY version"
                    ).fetchall()
            migrations.migrate(scoped)
            migrations.migrate(scoped)
            with psycopg.connect(scoped) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT relkind FROM pg_class WHERE oid='account_runs'::regclass"
                    ).fetchone()[0],
                    "v",
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT relkind FROM pg_class WHERE oid='workflow_runs'::regclass"
                    ).fetchone()[0],
                    "r",
                )
                columns = {
                    row[0]
                    for row in connection.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='account_runs'",
                        (schema,),
                    )
                }
                self.assertIn("parent_run_id", columns)
                if branch:
                    # Added columns may change SELECT *, so compare stable state explicitly.
                    value = connection.execute(
                        "SELECT id,session_id,turn_id,state,config,result FROM workflow_runs WHERE id=%s",
                        (run[0],),
                    ).fetchone()
                    self.assertEqual(
                        value[1:],
                        (
                            "paid-session",
                            "paid-turn",
                            "review",
                            {"review_mode": "all_outputs"},
                            {"records": []},
                        ),
                    )
                    for version, checksum in before:
                        self.assertEqual(
                            connection.execute(
                                "SELECT checksum FROM schema_migrations WHERE version=%s",
                                (version,),
                            ).fetchone()[0],
                            checksum,
                        )
                    connection.execute(
                        "UPDATE account_runs SET parent_run_id=id WHERE id=%s", (run[0],)
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT parent_run_id FROM workflow_runs WHERE id=%s", (run[0],)
                        ).fetchone()[0],
                        run[0],
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT status FROM workflows WHERE id=%s", (workflow,)
                        ).fetchone()[0],
                        "paused",
                    )
        finally:
            with psycopg.connect(URL, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
