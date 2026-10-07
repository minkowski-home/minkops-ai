"""Prove logical restore into a newly created disposable Cloud SQL database."""

import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from google_api import GoogleApi

STATE_DIR = Path.home() / ".local/state/minkops-deployment"


def main():
    state = json.loads((STATE_DIR / "database.json").read_text())
    admin = dict(host="127.0.0.1", port=5433, dbname="postgres",
                 user=state["bootstrap"], password=state["bootstrap_password"])
    restored = "minkops_restore_" + uuid4().hex[:12]
    dump = STATE_DIR / "minkops-before-launch.dump"
    # Credentials are child environment only, never command arguments/output.
    environment = dict(os.environ, PGHOST="127.0.0.1", PGPORT="5433", PGDATABASE="minkops",
                       PGUSER="minkops_migrate", PGPASSWORD=state["migration_password"],
                       PGOPTIONS="-c role=minkops_owner")
    # Match the production server major. Newer pg_dump can emit SET statements
    # unavailable on PostgreSQL 16 even when its source connection succeeds.
    binaries = Path("/usr/lib/postgresql/16/bin")
    subprocess.run([str(binaries / "pg_dump"), "--format=custom", "--no-owner", "--no-privileges", f"--file={dump}"],
                   env=environment, check=True, capture_output=True)
    os.chmod(dump, 0o600)
    with psycopg.connect(**admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER minkops_owner").format(sql.Identifier(restored)))
    environment.update(PGDATABASE=restored)
    subprocess.run([str(binaries / "pg_restore"), "--exit-on-error", "--no-owner", "--no-privileges", "--dbname=" + restored, str(dump)],
                   env=environment, check=True, capture_output=True)
    fingerprints = []
    for database in ("minkops", restored):
        with psycopg.connect(**dict(admin, dbname=database)) as connection:
            fingerprints.append((connection.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall(),
                                 connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall(),
                                 connection.execute("SELECT generation, acknowledged FROM worker_wakeup").fetchall()))
    if fingerprints[0] != fingerprints[1]:
        raise RuntimeError("Restore mismatch; temporary database preserved for inspection")
    with psycopg.connect(**admin, autocommit=True) as connection:
        # This name was generated and created in this invocation, never supplied.
        connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(restored)))
    api = GoogleApi("minkops-ai-prod")
    operation = api.request("https://sqladmin.googleapis.com/v1/projects/myndral-prod/instances/myndral-db/users?name=" + state["bootstrap"], method="DELETE")
    api.wait("https://sqladmin.googleapis.com/v1/projects/myndral-prod/operations/" + operation["name"])
    print(f"Logical restore verified: {len(fingerprints[0][1])} tables, {len(fingerprints[0][0])} migrations. Temporary database and bootstrap login removed.")


if __name__ == "__main__":
    main()
