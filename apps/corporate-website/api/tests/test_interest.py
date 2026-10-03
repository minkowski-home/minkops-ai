import asyncio

import pytest
from fastapi.testclient import TestClient

from minkops_corporate_website_api import main


@pytest.fixture
def client(monkeypatch):
    main.app.state.interest_limiter = main.SlidingWindowLimiter()
    main.app.state.delivery_guard = main.DeliveryGuard()
    sent = []

    async def fake_send(payload):
        sent.append(payload)
        return "<interest-test@minkops.com>"

    monkeypatch.setattr(main, "_send_with_workspace_smtp", fake_send)
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
    assert response.json() == {"status": "accepted"}
    assert len(sent) == 1


def test_invalid_fields_are_rejected_before_delivery(client):
    test_client, sent = client

    response = test_client.post("/api/interest", json=valid_payload(email="not-an-email"))

    assert response.status_code == 422
    assert sent == []


def test_same_submission_is_sent_once(client):
    test_client, sent = client
    payload = valid_payload()

    first = test_client.post("/api/interest", json=payload)
    retry = test_client.post("/api/interest", json=payload)

    assert first.status_code == retry.status_code == 202
    assert first.json() == retry.json()
    assert len(sent) == 1


def test_concurrent_identical_submissions_share_one_smtp_attempt(monkeypatch):
    guard = main.DeliveryGuard()
    calls = 0

    async def fake_send(_payload):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "<interest-test@minkops.com>"

    monkeypatch.setattr(main, "_send_with_workspace_smtp", fake_send)
    payload = main.InterestSubmission(**valid_payload())

    async def submit_twice():
        return await asyncio.gather(
            guard.send(payload, "same-key"), guard.send(payload, "same-key")
        )

    first, second = asyncio.run(submit_twice())

    assert first == second == "<interest-test@minkops.com>"
    assert calls == 1


def test_provider_failure_is_reported_without_leaking_provider_details(client, monkeypatch):
    test_client, _ = client

    async def fail_send(_payload):
        raise main.DeliveryError("secret provider response")

    monkeypatch.setattr(main, "_send_with_workspace_smtp", fail_send)
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


def test_workspace_smtp_uses_fixed_target_sender_reply_to_and_escaped_content(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "private@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@minkops.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Minkops")
    captured = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    payload = main.InterestSubmission(**valid_payload())
    monkeypatch.setattr(main.aiosmtplib, "send", fake_send)
    message_id = asyncio.run(main._send_with_workspace_smtp(payload))
    message = captured["message"]

    assert message_id == message["Message-ID"]
    assert message["From"] == "Minkops <info@minkops.com>"
    assert message["To"] == "info@minkops.com"
    assert message["Reply-To"] == "alex@example.com"
    assert "&lt;reports&gt;" in message.get_body(preferencelist=("html",)).get_content()
    assert captured["kwargs"] == {
        "hostname": "smtp.gmail.com",
        "port": 587,
        "start_tls": True,
        "username": "private@example.test",
        "password": "not-a-real-password",
        "sender": "info@minkops.com",
        "recipients": ["info@minkops.com"],
        "timeout": 8,
    }


def test_delivery_fails_closed_without_workspace_configuration(monkeypatch):
    for name in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "SMTP_FROM_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(main.DeliveryError):
        asyncio.run(
            main._send_with_workspace_smtp(main.InterestSubmission(**valid_payload()))
        )


def test_smtp_timeout_is_ambiguous_and_identical_retry_is_suppressed(client, monkeypatch):
    test_client, _sent = client
    calls = 0

    async def timeout_after_attempt(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise main.DeliveryError(
            "Email acceptance could not be confirmed.", ambiguous=True
        )

    monkeypatch.setattr(main, "_send_with_workspace_smtp", timeout_after_attempt)
    payload = valid_payload()

    first = test_client.post("/api/interest", json=payload)
    retry = test_client.post("/api/interest", json=payload)

    assert first.status_code == retry.status_code == 503
    assert "Please don't submit it again" in first.json()["detail"]
    assert "Please don't submit it again" in first.json()["detail"]
    assert calls == 1


def test_workspace_smtp_rejects_non_google_hosts_and_non_public_from(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "private@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "private@example.test")
    monkeypatch.setenv("SMTP_FROM_NAME", "Minkops")

    with pytest.raises(main.DeliveryError):
        asyncio.run(
            main._send_with_workspace_smtp(main.InterestSubmission(**valid_payload()))
        )


def test_smtp_transport_error_is_classified_as_ambiguous(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "private@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@minkops.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Minkops")

    async def timeout(*_args, **_kwargs):
        raise TimeoutError("private transport diagnostic")

    monkeypatch.setattr(main.aiosmtplib, "send", timeout)

    with pytest.raises(main.DeliveryError) as error:
        asyncio.run(
            main._send_with_workspace_smtp(main.InterestSubmission(**valid_payload()))
        )
    assert error.value.ambiguous is True
    assert "private transport diagnostic" not in str(error.value)
