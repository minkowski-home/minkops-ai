"""Prove logical restore into a newly created disposable Cloud SQL database.

Run through the same loopback proxy, against the same instance and state, as
provision_database.py; it removes that instance's bootstrap login when done.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from google_api import GoogleApi
from psycopg import sql


def client_tools(bindir, environment):
    """PostgreSQL 16's pg_dump and pg_restore, from `bindir` when given, else from PATH.

    Match the production server major. Newer pg_dump can emit SET statements
    unavailable on PostgreSQL 16 even when its source connection succeeds.
    """
    where = f"in {bindir}" if bindir else "on PATH"
    tools = {}
    for name in ("pg_dump", "pg_restore"):
        path = shutil.which(bindir / name if bindir else name)
        if not path:
            raise RuntimeError(f"No {name} {where}; name PostgreSQL 16's bin directory with --pg-bindir.")
        # The restore's own environment, so a version-selecting wrapper (Debian's
        # pg_wrapper) reports the binary the restore will run.
        version = subprocess.check_output([path, "--version"], env=environment, text=True)
        if not re.match(rf"{name} \(PostgreSQL\) 16\.", version):
            raise RuntimeError(f"{path} reports {version.strip()!r}, not PostgreSQL 16; "
                               "name 16's bin directory with --pg-bindir.")
        tools[name] = path
    return tools


def main(project, instance, state_dir, port, bindir):
    state = json.loads((state_dir / "database.json").read_text())
    admin = {"host": "127.0.0.1", "port": port, "dbname": "postgres",
             "user": state["bootstrap"], "password": state["bootstrap_password"]}
    restored = "minkops_restore_" + uuid4().hex[:12]
    dump = state_dir / "minkops-before-launch.dump"
    # Credentials are child environment only, never command arguments/output.
    environment = dict(os.environ, PGHOST="127.0.0.1", PGPORT=str(port), PGDATABASE="minkops",
                       PGUSER="minkops_migrate", PGPASSWORD=state["migration_password"],
                       PGOPTIONS="-c role=minkops_owner")
    tools = client_tools(bindir, environment)
    subprocess.run([tools["pg_dump"], "--format=custom", "--no-owner", "--no-privileges", f"--file={dump}"],
                   env=environment, check=True, capture_output=True)
    os.chmod(dump, 0o600)
    with psycopg.connect(**admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER minkops_owner").format(sql.Identifier(restored)))
    environment.update(PGDATABASE=restored)
    subprocess.run([tools["pg_restore"], "--exit-on-error", "--no-owner", "--no-privileges", "--dbname=" + restored, str(dump)],
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
    base = f"https://sqladmin.googleapis.com/v1/projects/{project}"
    operation = api.request(f"{base}/instances/{instance}/users?name=" + state["bootstrap"], method="DELETE")
    api.wait(f"{base}/operations/" + operation["name"])
    print(f"Logical restore verified: {len(fingerprints[0][1])} tables, {len(fingerprints[0][0])} migrations. Temporary database and bootstrap login removed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-project", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--proxy-port", type=int, default=5433,
                        help="Local port of the Cloud SQL Auth Proxy to the instance (default %(default)s).")
    parser.add_argument("--pg-bindir", type=Path,
                        help="PostgreSQL 16's bin directory for pg_dump and pg_restore; PATH when omitted.")
    args = parser.parse_args()
    main(args.sql_project, args.instance, args.state_dir, args.proxy_port, args.pg_bindir)
