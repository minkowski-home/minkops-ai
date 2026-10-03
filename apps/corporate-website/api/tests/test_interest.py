import json

import pytest
from fastapi.testclient import TestClient

from minkops_corporate_website_api import main


@pytest.fixture
def client(monkeypatch):
    main.app.state.interest_limiter = main.SlidingWindowLimiter()
    sent = []

    async def fake_send(payload, idempotency_key):
        sent.append((payload, idempotency_key))
        return "email_test_123"

    monkeypatch.setattr(main, "send_interest_email", fake_send)
    return TestClient(main.app), sent


def valid_payload(**overrides):
    return {
        "name": "Alex Visitor",
        "email": "alex@example.com",
        "company": "Example Co",
        "interest": "operations",
        "message": "We need help with <reports>.",
        **overrides,
    }


def test_valid_submission_returns_provider_acceptance_and_fixed_recipient(client):
    test_client, sent = client

    response = test_client.post("/api/interest", json=valid_payload())

    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "message_id": "email_test_123"}
    assert len(sent) == 1


def test_invalid_fields_are_rejected_before_delivery(client):
    test_client, sent = client

    response = test_client.post("/api/interest", json=valid_payload(email="not-an-email"))

    assert response.status_code == 422
    assert sent == []


def test_same_submission_uses_stable_provider_idempotency_key(client):
    test_client, sent = client
    payload = valid_payload()

    first = test_client.post("/api/interest", json=payload)
    retry = test_client.post("/api/interest", json=payload)

    assert first.status_code == retry.status_code == 202
    assert sent[0][1] == sent[1][1]


def test_provider_failure_is_reported_without_leaking_provider_details(client, monkeypatch):
    test_client, _ = client

    async def fail_send(_payload, _idempotency_key):
        raise main.DeliveryError("secret provider response")

    monkeypatch.setattr(main, "send_interest_email", fail_send)
    response = test_client.post("/api/interest", json=valid_payload())

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "We couldn't send your note yet. Please try again or email info@minkops.com."
    )
    assert "secret provider response" not in response.text


def test_rate_limit_and_honeypot_prevent_delivery(client):
    test_client, sent = client

    trapped = test_client.post("/api/interest", json=valid_payload(website="bot.example"))
    assert trapped.status_code == 202
    assert trapped.json() == {"status": "accepted"}
    assert sent == []

    for _ in range(4):
        assert test_client.post("/api/interest", json=valid_payload()).status_code == 202
    limited = test_client.post("/api/interest", json=valid_payload())
    assert limited.status_code == 429


def test_cors_allows_local_frontend_submission(client):
    test_client, _ = client

    response = test_client.options(
        "/api/interest",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_invalid_requests_consume_rate_limit(client):
    test_client, sent = client

    for _ in range(5):
        assert (
            test_client.post(
                "/api/interest", json=valid_payload(email="invalid")
            ).status_code
            == 422
        )

    assert test_client.post("/api/interest", json=valid_payload()).status_code == 429
    assert sent == []


def test_resend_request_uses_fixed_target_and_escaped_content(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test_secret")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Minkops <hello@minkops.com>")
    captured = {}

    class Response:
        status = 200

        def read(self):
            return b'{"id":"email_test_123"}'

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data)
        return Response()

    payload = main.InterestSubmission(**valid_payload())
    message_id = main._send_with_resend(payload, "stable-key", opener=opener)

    assert message_id == "email_test_123"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer test_secret"
    assert captured["headers"]["Idempotency-key"] == "stable-key"
    assert captured["payload"]["to"] == ["info@minkops.com"]
    assert captured["payload"]["reply_to"] == "alex@example.com"
    assert "&lt;reports&gt;" in captured["payload"]["html"]
    assert captured["timeout"] == 8


def test_delivery_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)

    with pytest.raises(main.DeliveryError):
        main._send_with_resend(main.InterestSubmission(**valid_payload()), "stable-key")
