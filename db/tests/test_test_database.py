"""Test setup must never write fixtures into the supplied application database."""

import os
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict

from db.testing import disposable_database
from db.migrate import MIGRATIONS


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class TestDatabaseIsolation(unittest.TestCase):
    def test_disposable_database_preserves_source_and_cleans_up_after_failure(self):
        source = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(source) as connection:
            before = connection.execute("SELECT count(*) FROM desktop_devices").fetchone()
        with (
            self.assertRaisesRegex(RuntimeError, "simulated failure"),
            disposable_database(source) as isolated,
        ):
            name = conninfo_to_dict(isolated)["dbname"]
            self.assertNotEqual(name, conninfo_to_dict(source)["dbname"])
            with psycopg.connect(isolated) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM desktop_devices").fetchone()[0], 0
                )
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0],
                    len(list(MIGRATIONS.glob("*.sql"))),
                )
            raise RuntimeError("simulated failure")
        with psycopg.connect(source) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM desktop_devices").fetchone(), before
            )
            self.assertIsNone(
                connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone()
            )
