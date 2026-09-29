"""Integration checks for the clean OLTP baseline.

Run against a disposable PostgreSQL database with TEST_DATABASE_URL set.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class MigrationTests(unittest.TestCase):
    def test_baseline_is_repeatable_and_scoped(self):
        for _ in range(2):
            subprocess.run([sys.executable, "-m", "minkops_db.migrate"], cwd=ROOT,
                           env={**os.environ, "DATABASE_URL": URL}, check=True)

        with psycopg.connect(URL) as connection:
            names = {row[0] for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
            self.assertTrue({"tenants", "users", "memberships", "employees",
                             "workflows", "workflow_employees", "tasks",
                             "task_events", "event_outbox", "schema_migrations"} <= names)
            self.assertFalse({"agent_state", "agent_intercom_queue", "tickets"} & names)
            self.assertEqual(connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 1)

    def test_cross_tenant_workflow_employee_link_is_rejected(self):
        subprocess.run([sys.executable, "-m", "minkops_db.migrate"], cwd=ROOT,
                       env={**os.environ, "DATABASE_URL": URL}, check=True)
        with psycopg.connect(URL) as connection:
            with connection.transaction():
                first = connection.execute("INSERT INTO tenants (slug, name) VALUES ('migration-a', 'A') RETURNING id").fetchone()[0]
                second = connection.execute("INSERT INTO tenants (slug, name) VALUES ('migration-b', 'B') RETURNING id").fetchone()[0]
                employee = connection.execute("INSERT INTO employees (tenant_id, key, name) VALUES (%s, 'one', 'One') RETURNING id", (first,)).fetchone()[0]
                workflow = connection.execute("INSERT INTO workflows (tenant_id, key, name) VALUES (%s, 'two', 'Two') RETURNING id", (second,)).fetchone()[0]
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                connection.execute("INSERT INTO workflow_employees (tenant_id, workflow_id, employee_id) VALUES (%s, %s, %s)", (first, workflow, employee))
            connection.rollback()
            connection.execute("DELETE FROM tenants WHERE id IN (%s, %s)", (first, second))


if __name__ == "__main__":
    unittest.main()
