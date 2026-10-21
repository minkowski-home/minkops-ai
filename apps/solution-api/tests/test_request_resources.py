"""Request resource budgets without starting cloud jobs or paid sessions."""
import asyncio
import os
from unittest.mock import patch

import psycopg
import pytest
from starlette.requests import Request
from starlette.responses import Response

from minkops_api.auth import close_database_pool, database_pool
from minkops_api.main import private_api_cache


def test_read_polling_does_not_attempt_dispatch():
    async def check():
        async def reply(_):
            return Response(status_code=200)
        with patch.dict(os.environ, WORKER_JOB_RESOURCE="test-job"):
            for method in ("GET", "HEAD", "OPTIONS"):
                response = await private_api_cache(Request({"type": "http", "method": method,
                    "path": "/api/auth/session", "headers": []}), reply)
                assert response.background is None
            response = await private_api_cache(Request({"type": "http", "method": "POST",
                "path": "/api/desktop/worker/heartbeat", "headers": []}), reply)
            assert response.background is not None
    asyncio.run(check())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
def test_request_pool_reuses_connection_and_rolls_back_failed_transaction(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    close_database_pool()
    pool = database_pool()
    with pool.connection() as connection:
        first = connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
    with pytest.raises(psycopg.errors.DivisionByZero), pool.connection() as connection:
        connection.execute("SELECT 1/0")
    with pool.connection() as connection:
        assert connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"] == first
