"""Isolate database-backed pytest suites before modules capture their URLs."""

import os

from db.testing import disposable_database


def pytest_configure(config):
    server_url = os.getenv("TEST_DATABASE_URL")
    if not server_url:
        return
    context = disposable_database(server_url)
    isolated_url = context.__enter__()
    config._minkops_test_database = context
    config._minkops_previous_environment = {
        key: os.getenv(key) for key in ("TEST_DATABASE_URL", "DATABASE_URL")
    }
    os.environ["TEST_DATABASE_URL"] = isolated_url
    os.environ["DATABASE_URL"] = isolated_url


def pytest_unconfigure(config):
    context = getattr(config, "_minkops_test_database", None)
    if context is None:
        return
    try:
        context.__exit__(None, None, None)
    finally:
        for key, value in config._minkops_previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
