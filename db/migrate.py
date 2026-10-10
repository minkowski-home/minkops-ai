"""Apply the final baseline or adopt verified legacy history without rebuilding data."""

import hashlib
import os
from pathlib import Path

import psycopg


MIGRATIONS = Path(__file__).resolve().with_name("migrations")
ARCHIVE = Path(__file__).resolve().parent / "archive/pre-baseline"
BASELINE = "0001_baseline"


def sources(directory):
    result = {}
    for path in sorted(directory.glob("*.sql")):
        source = path.read_bytes()
        result[path.stem] = (source, hashlib.sha256(source).hexdigest())
    return result


def apply(connection, version, source, checksum):
    connection.execute(source.decode())
    connection.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                       (version, checksum))


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
            current, legacy = sources(MIGRATIONS), sources(ARCHIVE)
            known = {**legacy, **current}
            for version, checksum in applied.items():
                if version not in known:
                    raise RuntimeError(f"Unknown migration history: {version}")
                if checksum != known[version][1]:
                    raise RuntimeError(f"Applied migration changed: {version}.sql")
            if BASELINE not in applied and applied:
                # Converge either released branch with its original SQL/checksums.
                # Preserve runs, sessions, reservations and receipts, then adopt
                # the equivalent baseline. No baseline CREATE executes here.
                for version, (source, checksum) in legacy.items():
                    if version not in applied:
                        apply(connection, version, source, checksum)
                connection.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                                   (BASELINE, current[BASELINE][1]))
                applied[BASELINE] = current[BASELINE][1]
            for version, (source, checksum) in current.items():
                if version in applied:
                    continue
                apply(connection, version, source, checksum)


if __name__ == "__main__":
    migrate(os.environ["DATABASE_URL"])
