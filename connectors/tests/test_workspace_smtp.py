import asyncio

import pytest

from minkops_connectors import workspace_smtp
from minkops_connectors import smtp_diagnostics


def _configure(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp-relay.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "workspace-user@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@minkops.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Minkops")


class FakeSmtp:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.calls = []

    async def connect(self):
        self.calls.append(("connect",))

    async def login(self, username, password):
        self.calls.append(("login", username, password))

    async def send_message(self, message, **kwargs):
        self.calls.append(("send_message", message, kwargs))

    async def quit(self):
        self.calls.append(("quit",))


@pytest.mark.parametrize("host", ["smtp-relay.gmail.com", "smtp.gmail.com"])
def test_sends_fixed_recipient_and_public_alias_with_visitor_reply_to(monkeypatch, host):
    _configure(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", host)
    captured = {}

    def fake_smtp(**kwargs):
        client = FakeSmtp(**kwargs)
        captured["client"] = client
        return client

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "SMTP", fake_smtp)
    message_id = asyncio.run(
        workspace_smtp.send_discovery_notification(
            name="Alex <Visitor>",
            email="alex@example.test",
            company="Example Co",
            interest="operations",
            message="Please review <this>.",
        )
    )

    client = captured["client"]
    message = client.calls[2][1]
    assert message_id == message["Message-ID"]
    assert message["From"] == "Minkops <info@minkops.com>"
    assert message["To"] == "info@minkops.com"
    assert message["Reply-To"] == "alex@example.test"
    assert "&lt;this&gt;" in message.get_body(preferencelist=("html",)).get_content()
    assert client.options == {
        "hostname": host,
        "port": 587,
        "local_hostname": "minkops.com",
        "start_tls": True,
        "timeout": 8,
    }
    assert [call[0] for call in client.calls] == ["connect", "login", "send_message", "quit"]
    assert client.calls[1] == ("login", "workspace-user@example.test", "test-only-password")
    assert client.calls[2][2] == {
        "sender": "info@minkops.com",
        "recipients": ["info@minkops.com"],
    }


def test_requires_workspace_relay_configuration(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")

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


def test_connect_failure_is_definitive_and_logged_without_provider_details(monkeypatch, caplog):
    _configure(monkeypatch)

    class ConnectFailure(FakeSmtp):
        async def connect(self):
            raise RuntimeError("private provider diagnostic")

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "SMTP", ConnectFailure)
    with pytest.raises(workspace_smtp.SmtpSetupFailure) as error:
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
    assert "phase=connect_or_tls" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "private provider diagnostic" not in caplog.text


def test_explicit_smtp_refusal_is_not_ambiguous_and_logs_only_safe_metadata(monkeypatch, caplog):
    _configure(monkeypatch)

    class AuthenticationFailure(FakeSmtp):
        async def login(self, _username, _password):
            raise workspace_smtp.aiosmtplib.errors.SMTPAuthenticationError(
                535, "private account/provider details"
            )

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "SMTP", AuthenticationFailure)
    with pytest.raises(workspace_smtp.SmtpSetupFailure):
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.test",
                company="",
                interest="unsure",
                message="private body marker",
            )
        )
    output = caplog.text
    assert "phase=authentication" in output
    assert "SMTPAuthenticationError" in output
    assert "535" in output
    assert "private account/provider details" not in output
    assert "private body marker" not in output


def test_ambiguous_send_failure_logs_class_without_provider_message(monkeypatch, caplog):
    _configure(monkeypatch)

    class SendFailure(FakeSmtp):
        async def send_message(self, *_args, **_kwargs):
            raise RuntimeError("private provider diagnostic")

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "SMTP", SendFailure)
    with pytest.raises(workspace_smtp.SmtpOutcomeUncertain):
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.test",
                company="",
                interest="unsure",
                message="",
            )
        )
    assert "phase=message_outcome_uncertain" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "private provider diagnostic" not in caplog.text


def test_explicit_data_rejection_is_definitive_and_logs_numeric_code(monkeypatch, caplog):
    _configure(monkeypatch)

    class DataRejected(FakeSmtp):
        async def send_message(self, *_args, **_kwargs):
            raise workspace_smtp.aiosmtplib.errors.SMTPDataError(
                550, "private relay policy text"
            )

    monkeypatch.setattr(workspace_smtp.aiosmtplib, "SMTP", DataRejected)
    with pytest.raises(workspace_smtp.SmtpRejected):
        asyncio.run(
            workspace_smtp.send_discovery_notification(
                name="Alex",
                email="alex@example.test",
                company="",
                interest="unsure",
                message="",
            )
        )
    assert "phase=message_rejected" in caplog.text
    assert "SMTPDataError" in caplog.text
    assert "response_code=550" in caplog.text
    assert "private relay policy text" not in caplog.text


def test_preflight_connects_and_authenticates_without_sending(monkeypatch):
    _configure(monkeypatch)
    captured = {}

    def fake_smtp(**kwargs):
        client = FakeSmtp(**kwargs)
        captured["client"] = client
        return client

    monkeypatch.setattr(smtp_diagnostics.aiosmtplib, "SMTP", fake_smtp)
    result = asyncio.run(smtp_diagnostics.check_relay())

    assert result == smtp_diagnostics.DiagnosticResult("authenticated")
    assert [call[0] for call in captured["client"].calls] == ["connect", "login", "quit"]


def test_preflight_reports_auth_class_and_code_without_private_text(monkeypatch):
    _configure(monkeypatch)

    class AuthenticationFailure(FakeSmtp):
        async def login(self, *_args):
            raise workspace_smtp.aiosmtplib.errors.SMTPAuthenticationError(
                535, "private provider detail"
            )

    monkeypatch.setattr(smtp_diagnostics.aiosmtplib, "SMTP", AuthenticationFailure)
    result = asyncio.run(smtp_diagnostics.check_relay())
    assert result == smtp_diagnostics.DiagnosticResult(
        "authentication", "SMTPAuthenticationError", 535, "authentication_rejected"
    )
    assert "private provider detail" not in repr(result)


def test_preflight_redacts_temporary_relay_text_to_safe_category(monkeypatch):
    _configure(monkeypatch)

    class TemporaryRelayFailure(FakeSmtp):
        async def connect(self):
            raise workspace_smtp.aiosmtplib.errors.SMTPHeloError(
                421, "Try again later for private-domain.example"
            )

    monkeypatch.setattr(smtp_diagnostics.aiosmtplib, "SMTP", TemporaryRelayFailure)
    result = asyncio.run(smtp_diagnostics.check_relay())
    assert result == smtp_diagnostics.DiagnosticResult(
        "connect_or_tls",
        "SMTPHeloError",
        421,
        "temporary_service_unavailable",
    )
    assert "private-domain.example" not in repr(result)
