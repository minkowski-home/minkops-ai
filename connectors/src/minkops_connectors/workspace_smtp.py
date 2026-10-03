"""Google Workspace SMTP adapter for discovery form notifications."""

from __future__ import annotations

import html
import os
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib

RECIPIENT = "info@minkops.com"
PUBLIC_SENDER = "info@minkops.com"
SMTP_HOST = "smtp-relay.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 8


class SmtpConfigurationError(Exception):
    """The deployment is missing the expected Workspace sender settings."""


class SmtpOutcomeUncertain(Exception):
    """SMTP stopped responding after a send attempt began."""


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
    try:
        await aiosmtplib.send(
            mail,
            hostname=host,
            port=SMTP_PORT,
            start_tls=True,
            username=username,
            password=password,
            sender=sender,
            recipients=[RECIPIENT],
            timeout=SMTP_TIMEOUT_SECONDS,
        )
    except Exception:
        # SMTP may accept DATA before a timeout/disconnect reaches this client.
        raise SmtpOutcomeUncertain(
            "Email acceptance could not be confirmed."
        ) from None
    return message_id
