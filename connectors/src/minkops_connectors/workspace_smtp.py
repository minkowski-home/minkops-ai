"""Google Workspace SMTP adapter for discovery form notifications."""

from __future__ import annotations

import html
import logging
import os
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib
from aiosmtplib.errors import SMTPRecipientsRefused, SMTPResponseException

RECIPIENT = "info@minkops.com"
PUBLIC_SENDER = "info@minkops.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 8
logger = logging.getLogger(__name__)


class SmtpConfigurationError(Exception):
    """The deployment is missing the expected Workspace sender settings."""


class SmtpOutcomeUncertain(Exception):
    """SMTP stopped responding after a send attempt began."""


class SmtpSetupFailure(Exception):
    """The SMTP connection or authentication failed before message submission."""


class SmtpRejected(Exception):
    """The SMTP server explicitly rejected a message before accepting it."""


def _log_smtp_failure(phase: str, error: Exception) -> None:
    """Log only safe diagnostic metadata, never provider text or message data."""

    code = getattr(error, "code", None)
    if not isinstance(code, int) or not 100 <= code <= 599:
        code = None
    reason = str(error).lower()
    if type(error).__name__ == "SMTPAuthenticationError":
        category = "authentication_rejected"
    elif any(term in reason for term in ("try again later", "server busy", "service isn't available")):
        category = "temporary_service_unavailable"
    elif any(term in reason for term in ("relay denied", "not authorized", "not registered")):
        category = "relay_policy_rejected"
    elif any(term in reason for term in ("invalid credentials", "authentication failed")):
        category = "authentication_rejected"
    elif code is not None and 400 <= code < 500:
        category = "temporary_smtp_failure"
    elif code is not None and 500 <= code < 600:
        category = "permanent_smtp_failure"
    else:
        category = "unknown_smtp_failure"
    logger.warning(
        "Workspace SMTP failed phase=%s error_class=%s response_code=%s category=%s",
        phase,
        type(error).__name__,
        code,
        category,
    )


def _render_message(
    *, name: str, email: str, company: str, interest: str, message: str
) -> tuple[str, str]:
    lines = [
        "A visitor submitted the Minkops discovery form.",
        "",
        f"Name: {name}",
        f"Email: {email}",
        f"Company: {company or 'Not provided'}",
        f"Interested in: {interest}",
        "",
        "Additional context:",
        message or "Not provided",
    ]
    text_body = "\n".join(lines)
    html_body = "<br>\n".join(html.escape(line) for line in lines)
    return text_body, f"<div>{html_body}</div>"


async def send_discovery_notification(
    *, name: str, email: str, company: str, interest: str, message: str
) -> str:
    """Send one fixed-recipient message through the public Minkops alias."""

    host = os.getenv("SMTP_HOST", "").strip().lower()
    raw_port = os.getenv("SMTP_PORT", "").strip()
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip().lower()
    sender_name = os.getenv("SMTP_FROM_NAME", "").strip()
    if (
        host != SMTP_HOST
        or raw_port != str(SMTP_PORT)
        or not username
        or not password
        or sender != PUBLIC_SENDER
        or not sender_name
        or any(char in sender_name for char in "\r\n")
    ):
        raise SmtpConfigurationError("Email delivery is not configured")

    text_body, html_body = _render_message(
        name=name, email=email, company=company, interest=interest, message=message
    )
    message_id = make_msgid(domain="minkops.com")
    mail = EmailMessage()
    mail["From"] = formataddr((sender_name, sender))
    mail["To"] = RECIPIENT
    mail["Reply-To"] = email
    mail["Subject"] = "New Minkops discovery request"
    mail["Message-ID"] = message_id
    mail.set_content(text_body)
    mail.add_alternative(html_body, subtype="html")
    client = aiosmtplib.SMTP(
        hostname=host,
        port=SMTP_PORT,
        local_hostname="minkops.com",
        start_tls=True,
        timeout=SMTP_TIMEOUT_SECONDS,
    )
    connected = False
    try:
        try:
            await client.connect()
            connected = True
        except Exception as exc:
            _log_smtp_failure("connect_or_tls", exc)
            raise SmtpSetupFailure("SMTP connection could not be established") from None

        try:
            await client.login(username, password)
        except Exception as exc:
            _log_smtp_failure("authentication", exc)
            raise SmtpSetupFailure("SMTP authentication failed") from None

        try:
            await client.send_message(mail, sender=sender, recipients=[RECIPIENT])
        except (SMTPResponseException, SMTPRecipientsRefused) as exc:
            # A complete negative SMTP response confirms this message was refused.
            _log_smtp_failure("message_rejected", exc)
            raise SmtpRejected("SMTP server rejected the message") from None
        except Exception as exc:
            # A disconnect while sending DATA may follow server acceptance.
            _log_smtp_failure("message_outcome_uncertain", exc)
            raise SmtpOutcomeUncertain(
                "Email acceptance could not be confirmed."
            ) from None
    finally:
        if connected:
            try:
                await client.quit()
            except Exception as exc:
                _log_smtp_failure("connection_cleanup", exc)
    return message_id
