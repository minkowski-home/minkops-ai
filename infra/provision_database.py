"""Provision isolated Minkops roles/database through a loopback SQL proxy.

Run explicitly as a cloud operator. The private state directory makes interrupted
provisioning resumable without rotating credentials of a running deployment.
The temporary bootstrap account is removed only after migration/grant checks.
"""

import argparse
import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from google_api import GoogleApi
from db.migrate import migrate, MIGRATIONS, sources


def provision(project, instance, state_dir):
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    state_path = state_dir / "database.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        state = {"bootstrap": "minkops_bootstrap", "bootstrap_password": secrets.token_urlsafe(40),
                 "runtime_password": secrets.token_urlsafe(40),
                 "migration_password": secrets.token_urlsafe(40)}
        descriptor = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream)
    api = GoogleApi("minkops-ai-prod")
    base = f"https://sqladmin.googleapis.com/v1/projects/{project}"
    users = api.request(f"{base}/instances/{instance}/users").get("items", [])
    if not any(user["name"] == state["bootstrap"] for user in users):
        operation = api.request(f"{base}/instances/{instance}/users",
                                {"name": state["bootstrap"], "password": state["bootstrap_password"]})
        api.wait(f"{base}/operations/{operation['name']}")
    admin = make_conninfo(host="127.0.0.1", port=5433, dbname="postgres",
                         user=state["bootstrap"], password=state["bootstrap_password"])
    with psycopg.connect(admin, autocommit=True) as connection:
        for name, password, limit in (("minkops_owner", None, -1),
                                      ("minkops_app", state["runtime_password"], 16),
                                      ("minkops_migrate", state["migration_password"], 3)):
            if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone():
                connection.execute(sql.SQL("CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT {} {}").format(
                    sql.Identifier(name), sql.SQL("LOGIN" if password else "NOLOGIN"),
                    sql.Literal(limit), sql.SQL("PASSWORD {}").format(sql.Literal(password)) if password else sql.SQL("")))
        connection.execute(sql.SQL("GRANT minkops_owner TO {}, minkops_migrate").format(sql.Identifier(state["bootstrap"])))
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname='minkops'").fetchone():
            connection.execute("CREATE DATABASE minkops OWNER minkops_owner")
        connection.execute("REVOKE ALL ON DATABASE minkops FROM PUBLIC")
        connection.execute("GRANT CONNECT ON DATABASE minkops TO minkops_app, minkops_migrate")
    migration_url = make_conninfo(host="127.0.0.1", port=5433, dbname="minkops",
                                 user="minkops_migrate", password=state["migration_password"],
                                 options="-c role=minkops_owner")
    migrate(migration_url)
    with psycopg.connect(migration_url) as connection:
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT USAGE ON SCHEMA public TO minkops_app")
        connection.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO minkops_app")
        connection.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO minkops_app")
        connection.execute("ALTER DEFAULT PRIVILEGES FOR ROLE minkops_owner IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO minkops_app")
        connection.execute("ALTER DEFAULT PRIVILEGES FOR ROLE minkops_owner IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO minkops_app")
    runtime_url = make_conninfo(host="127.0.0.1", port=5433, dbname="minkops",
                               user="minkops_app", password=state["runtime_password"])
    with psycopg.connect(runtime_url) as connection:
        applied = dict(connection.execute("SELECT version,checksum FROM schema_migrations").fetchall())
        assert all(applied.get(version) == checksum for version, (_, checksum) in sources(MIGRATIONS).items())
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        try:
            connection.execute("CREATE TABLE forbidden_runtime_ddl(id integer)")
        except psycopg.errors.InsufficientPrivilege:
            connection.rollback()
        else:
            connection.rollback()
            raise RuntimeError("Runtime unexpectedly has DDL privileges")
    print("Minkops database migrated; empty users; runtime DDL denied. Bootstrap retained for restore verification.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-project", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    provision(args.sql_project, args.instance, args.state_dir)
