"""The dedicated instance is created once, isolated and recoverable, never altered.

Its database tools reach it only through the proxy port the operator gives, and the
restore check runs PostgreSQL 16's client tools or none at all.
"""
import json
import os
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from db.migrate import MIGRATIONS, sources
from infra import provision_database, verify_database_restore

STATE = json.dumps({"bootstrap": "minkops_bootstrap", "bootstrap_password": "bootstrap-pw",
                    "runtime_password": "runtime-pw", "migration_password": "migrate-pw"})
SIXTEEN = {"pg_dump": "16.15", "pg_restore": "16.15"}


class Api:
    def __init__(self, existing=None):
        self.existing, self.calls = existing, []

    def request(self, url, body=None, *, method=None):
        self.calls.append((url, body))
        if body is None and url.endswith("/instances/minkops-books"):
            if self.existing is None:
                raise RuntimeError("Google API 404: sqladmin.googleapis.com/v1/projects/p/instances/minkops-books")
            return self.existing
        return {"name": "operation-1"}

    def wait(self, url, *, timeout=600):
        self.calls.append((url, "wait"))
        return {"done": True}


def test_a_missing_instance_is_created_as_encrypted_postgres_16_with_point_in_time_recovery():
    api = Api()
    assert provision_database.ensure_instance(api, "minkops-ai-prod", "minkops-books", "us-central1", "db-g1-small", 10)
    (_, body), = [call for call in api.calls if isinstance(call[1], dict)]
    settings = body["settings"]
    assert body["databaseVersion"] == "POSTGRES_16" and settings["tier"] == "db-g1-small"
    assert settings["backupConfiguration"]["pointInTimeRecoveryEnabled"] is True
    assert settings["ipConfiguration"] == {"ipv4Enabled": True, "sslMode": "ENCRYPTED_ONLY", "authorizedNetworks": []}
    assert settings["deletionProtectionEnabled"] is True
    assert api.calls[-1] == ("https://sqladmin.googleapis.com/v1/projects/minkops-ai-prod/operations/operation-1", "wait")


def test_an_existing_instance_is_left_unchanged_and_must_be_postgres_16():
    api = Api({"databaseVersion": "POSTGRES_16"})
    assert not provision_database.ensure_instance(api, "minkops-ai-prod", "minkops-books", "us-central1", "db-g1-small", 10)
    assert all(body is None for _, body in api.calls)
    with pytest.raises(RuntimeError, match="not PostgreSQL 16"):
        provision_database.ensure_instance(Api({"databaseVersion": "POSTGRES_15"}), "p", "minkops-books", "r", "t", 10)


def test_other_api_failures_are_never_mistaken_for_absence():
    class Failing(Api):
        def request(self, url, body=None, *, method=None):
            raise RuntimeError("Google API 403: sqladmin.googleapis.com")

    with pytest.raises(RuntimeError, match="403"):
        provision_database.ensure_instance(Failing(), "p", "minkops-books", "r", "t", 10)


class Instance:
    """The provisioned instance behind the operator's proxy, recording the address each connection reached.

    Every role, the database and every migration exist, users is empty, and the runtime role
    cannot create tables.
    """

    def __init__(self):
        self.reached = []

    def connect(self, conninfo="", *, autocommit=False, **params):
        info = conninfo_to_dict(make_conninfo(conninfo, **params))
        self.reached.append(f"{info['host']}:{info['port']}")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        if query == "CREATE TABLE forbidden_runtime_ddl(id integer)":
            raise psycopg.errors.InsufficientPrivilege()
        self.query = str(query)
        return self

    def fetchone(self):
        return (0,) if "count(*)" in self.query else (1,)

    def fetchall(self):
        # The same rows from every database, so a restored copy matches its source.
        return [(version, checksum) for version, (_, checksum) in sources(MIGRATIONS).items()]

    def rollback(self):
        pass


def tools(directory, **versions):
    """Stand-ins for PostgreSQL client tools in `directory`: each named tool reports its version."""
    directory.mkdir()
    for name, version in versions.items():
        (directory / name).write_text(f"#!/bin/sh\necho '{name} (PostgreSQL) {version} (Ubuntu {version}-1)'\n")
        (directory / name).chmod(0o755)
    return directory


def test_provisioning_reaches_the_instance_only_through_the_proxy_port_it_is_given(monkeypatch, tmp_path):
    instance = Instance()
    (tmp_path / "database.json").write_text(STATE)
    monkeypatch.setattr(provision_database, "GoogleApi", lambda project: Api())
    monkeypatch.setattr(provision_database.psycopg, "connect", instance.connect)
    # The migration runner opens its own connection from the URL it is given.
    monkeypatch.setattr(provision_database, "migrate", instance.connect)
    provision_database.provision("minkops-ai-prod", "minkops-books", tmp_path, 6543)
    assert instance.reached == ["127.0.0.1:6543"] * 4


def test_the_restore_check_reaches_the_instance_only_through_the_proxy_port_it_is_given(monkeypatch, tmp_path):
    instance, runs = Instance(), []
    (tmp_path / "database.json").write_text(STATE)
    monkeypatch.setattr(verify_database_restore, "GoogleApi", lambda project: Api())
    monkeypatch.setattr(verify_database_restore.psycopg, "connect", instance.connect)
    monkeypatch.setattr(verify_database_restore, "client_tools",
                        lambda bindir, environment: {"pg_dump": "pg_dump", "pg_restore": "pg_restore"})

    def run(command, *, env, **options):
        runs.append(f"{command[0]} {env['PGHOST']}:{env['PGPORT']}")
        for argument in command:
            if argument.startswith("--file="):
                Path(argument.removeprefix("--file=")).touch()

    monkeypatch.setattr(verify_database_restore.subprocess, "run", run)
    verify_database_restore.main("minkops-ai-prod", "minkops-books", tmp_path, 6543, None)
    assert instance.reached == ["127.0.0.1:6543"] * 4
    assert runs == ["pg_dump 127.0.0.1:6543", "pg_restore 127.0.0.1:6543"]


def test_restore_tools_come_from_the_named_directory_or_else_from_path(monkeypatch, tmp_path):
    sixteen, eighteen = tools(tmp_path / "16", **SIXTEEN), tools(tmp_path / "18", pg_dump="18.6", pg_restore="18.6")
    found = {name: str(sixteen / name) for name in SIXTEEN}
    monkeypatch.setenv("PATH", str(sixteen))
    assert verify_database_restore.client_tools(None, dict(os.environ)) == found
    monkeypatch.setenv("PATH", str(eighteen))
    assert verify_database_restore.client_tools(sixteen, dict(os.environ)) == found


@pytest.mark.parametrize(("on_path", "named", "refusal"), [
    ({"pg_dump": "18.6", "pg_restore": "18.6"}, None, r"path/pg_dump reports 'pg_dump \(PostgreSQL\) 18\.6"),
    (SIXTEEN, {"pg_dump": "15.8", "pg_restore": "15.8"}, r"named/pg_dump reports .*15\.8"),
    (SIXTEEN, {"pg_dump": "16.15", "pg_restore": "17.2"}, r"named/pg_restore reports .*17\.2"),
    ({}, None, "No pg_dump on PATH"),
    (SIXTEEN, {}, "No pg_dump in .*named"),
])
def test_the_restore_check_refuses_tools_that_are_not_postgres_16_before_touching_a_database(
        monkeypatch, tmp_path, on_path, named, refusal):
    monkeypatch.setenv("PATH", str(tools(tmp_path / "path", **on_path)))
    (tmp_path / "database.json").write_text(STATE)
    monkeypatch.setattr(verify_database_restore.psycopg, "connect", lambda *args, **kwargs: pytest.fail("A database was touched"))
    bindir = None if named is None else tools(tmp_path / "named", **named)
    with pytest.raises(RuntimeError, match=refusal):
        verify_database_restore.main("minkops-ai-prod", "minkops-books", tmp_path, 5433, bindir)
    assert not (tmp_path / "minkops-before-launch.dump").exists()
