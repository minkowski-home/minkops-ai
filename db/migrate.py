"""Apply ordered PostgreSQL migrations once, with checksum protection."""

import hashlib
import os
from pathlib import Path

import psycopg


MIGRATIONS = Path(__file__).with_name("migrations")


def migrate(url: str) -> None:
    with psycopg.connect(url) as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(481912)")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    checksum text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            applied = dict(connection.execute(
                "SELECT version, checksum FROM schema_migrations"
            ).fetchall())
            for path in sorted(MIGRATIONS.glob("*.sql")):
                source = path.read_bytes()
                checksum = hashlib.sha256(source).hexdigest()
                if path.stem in applied:
                    if applied[path.stem] != checksum:
                        raise RuntimeError(f"Applied migration changed: {path.name}")
                    continue
                connection.execute(source.decode())
                connection.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (path.stem, checksum),
                )


if __name__ == "__main__":
    migrate(os.environ["DATABASE_URL"])
