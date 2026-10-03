import asyncio

import pytest

from minkops_connectors import workspace_smtp


def _configure(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp-relay.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "workspace-user@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@minkops.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Minkops")


def test_sends_fixed_recipient_and_public_alias_with_visitor_reply_to(monkeypatch):
    _configure(monkeypatch)
    captured = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "send", fake_send)
    message_id = asyncio.run(
        workspace_smtp.send_discovery_notification(
            name="Alex <Visitor>",
            email="alex@example.test",
            company="Example Co",
            interest="operations",
            message="Please review <this>.",
        )
    )

    message = captured["message"]
    assert message_id == message["Message-ID"]
    assert message["From"] == "Minkops <info@minkops.com>"
    assert message["To"] == "info@minkops.com"
    assert message["Reply-To"] == "alex@example.test"
    assert "&lt;this&gt;" in message.get_body(preferencelist=("html",)).get_content()
    assert captured["kwargs"] == {
        "hostname": "smtp-relay.gmail.com",
        "port": 587,
        "start_tls": True,
        "username": "workspace-user@example.test",
        "password": "test-only-password",
        "sender": "info@minkops.com",
        "recipients": ["info@minkops.com"],
        "timeout": 8,
    }


def test_requires_workspace_relay_configuration(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")

    with pytest.raises(workspace_smtp.SmtpConfigurationError):
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.test",
                company="",
                interest="unsure",
                message="",
            )
        )


def test_smtp_failure_is_marked_ambiguous_without_provider_details(monkeypatch):
    _configure(monkeypatch)

    async def fail_send(*_args, **_kwargs):
        raise RuntimeError("private provider diagnostic")

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "send", fail_send)
    with pytest.raises(workspace_smtp.SmtpOutcomeUncertain) as error:
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.test",
                company="",
                interest="unsure",
                message="",
            )
        )
    assert "private provider diagnostic" not in str(error.value)
