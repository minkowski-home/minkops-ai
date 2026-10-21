"""The IAM-private recovery endpoint is a small transport over shared logic."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from minkops_api import operations


@pytest.mark.parametrize("dispatched", [False, True])
def test_reconciliation_uses_only_the_configured_database_and_job(monkeypatch, dispatched):
    recover = Mock(return_value=dispatched)
    monkeypatch.setenv("DATABASE_URL", "postgresql:///isolated-test")
    monkeypatch.setattr(operations, "recover", recover)
    with TestClient(operations.app) as client:
        response = client.post("/reconcile", json={"database_url": "ignored", "job": "ignored"})
    assert response.status_code == 200 and response.json() == {"dispatched": dispatched}
    recover.assert_called_once_with("postgresql:///isolated-test", operations.run_job)


def test_reconciliation_failure_does_not_expose_credentials_or_payloads(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "postgresql:///isolated-test")
    monkeypatch.setattr(operations, "recover", Mock(side_effect=RuntimeError("secret and business payload")))
    with TestClient(operations.app) as client:
        response = client.post("/reconcile")
    assert response.status_code == 503
    assert response.json() == {"detail": "Recovery is temporarily unavailable."}
    assert "secret and business payload" not in response.text + caplog.text


def test_unconfigured_service_fails_closed_without_running_recovery(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    recover = Mock()
    monkeypatch.setattr(operations, "recover", recover)
    with TestClient(operations.app) as client:
        assert client.post("/reconcile").status_code == 503
    recover.assert_not_called()


def test_no_read_method_or_documentation_routes_are_exposed():
    with TestClient(operations.app) as client:
        assert client.get("/reconcile").status_code == 405
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
