"""Apply the baseline to a fresh database, then every later migration in order.

A database whose history predates the baseline holds the parked build's work:
the rebuilt app starts on a fresh database instead (docs/rebuild/cutover.md).
Unknown or changed history fails the whole transaction, and an advisory lock
serializes runners.
"""

import hashlib
import os
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().with_name("migrations")
BASELINE = "0001_baseline"
# One verified formatting-only rewrite. Match BOTH digests so future edits to
# this migration still fail closed, including on installations of the old form.
BASELINE_FORMAT_CHECKSUMS = (
    "8add6cd28e9b81bc0ad179dfe20a160617f91e998163de03c3451a67ed478ba5",
    "87bf2818223328eb68b93ee3fd4c00149d1aca4aa5d61fad85c65f7fbdbf1e6f",
)


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
    with psycopg.connect(url) as connection, connection.transaction():
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
        if applied and BASELINE not in applied:
            raise RuntimeError("This database predates the baseline: it holds the parked build's work, and the "
                               "rebuilt app starts on a fresh database.")
        current = sources(MIGRATIONS)
        for version, checksum in applied.items():
            if version not in current:
                raise RuntimeError(f"Unknown migration history: {version}")
            equivalent_baseline = (
                version == BASELINE
                and (checksum, current[version][1]) == BASELINE_FORMAT_CHECKSUMS
            )
            if checksum != current[version][1] and not equivalent_baseline:
                raise RuntimeError(f"Applied migration changed: {version}.sql")
        for version, (source, checksum) in current.items():
            if version not in applied:
                apply(connection, version, source, checksum)


if __name__ == "__main__":
    migrate(os.environ["DATABASE_URL"])
