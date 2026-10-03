import asyncio

import pytest

from minkops_connectors import workspace_smtp


def set_workspace_config(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "private@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@minkops.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Minkops")


def test_smtp_adapter_uses_public_sender_fixed_recipient_and_safe_reply_to(monkeypatch):
    set_workspace_config(monkeypatch)
    captured = {}

    async def fake_send(mail, **kwargs):
        captured["mail"] = mail
        captured["kwargs"] = kwargs

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "send", fake_send)
    message_id = asyncio.run(
        workspace_smtp.send_discovery_notification(
            name="Alex Visitor",
            email="alex@example.com",
            company="Example Co",
            interest="operations",
            message="Need <reports>.",
        )
    )
    mail = captured["mail"]

    assert message_id == mail["Message-ID"]
    assert mail["From"] == "Minkops <info@minkops.com>"
    assert mail["To"] == "info@minkops.com"
    assert mail["Reply-To"] == "alex@example.com"
    assert "&lt;reports&gt;" in mail.get_body(preferencelist=("html",)).get_content()
    assert captured["kwargs"] == {
        "hostname": "smtp.gmail.com",
        "port": 587,
        "start_tls": True,
        "username": "private@example.test",
        "password": "test-only-password",
        "sender": "info@minkops.com",
        "recipients": ["info@minkops.com"],
        "timeout": workspace_smtp.SMTP_TIMEOUT_SECONDS,
    }


def test_adapter_fails_closed_when_workspace_configuration_is_missing(monkeypatch):
    for key in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "SMTP_FROM_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(workspace_smtp.SmtpConfigurationError) as error:
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.com",
                company="",
                interest="unsure",
                message="",
            )
        )
    assert "SMTP" not in str(error.value)


def test_transport_error_is_ambiguous_without_exposing_diagnostics(monkeypatch):
    set_workspace_config(monkeypatch)

    async def fail(*_args, **_kwargs):
        raise TimeoutError("private transport detail")

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "send", fail)
    with pytest.raises(workspace_smtp.SmtpOutcomeUncertain) as error:
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.com",
                company="",
                interest="unsure",
                message="",
            )
        )
    assert "private transport detail" not in str(error.value)
    assert "private@example.test" not in str(error.value)
