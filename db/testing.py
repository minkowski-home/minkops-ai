"""Disposable integration databases; the supplied URL grants server access only."""

from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from db.migrate import migrate
from db.seed_demo import seed_demo


@contextmanager
def disposable_database(server_url):
    parameters = conninfo_to_dict(server_url)
    # Never inherit an application-specific search_path or database name.
    parameters.pop("options", None)
    name = "minkops_pytest_" + uuid4().hex
    admin_url = make_conninfo(**{**parameters, "dbname": "postgres"})
    isolated_url = make_conninfo(**{**parameters, "dbname": name})
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            migrate(isolated_url)
            seed_demo(isolated_url, "long test password 123!")
            yield isolated_url
        finally:
            # Only this invocation's freshly created database can be dropped.
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
