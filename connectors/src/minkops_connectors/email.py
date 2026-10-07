"""Synchronous SMTP transport for first-party account messages."""

import os
import smtplib
import ssl


def send_email(message):
    with smtplib.SMTP(
        os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")),
        local_hostname=os.getenv("SMTP_EHLO_HOST", "minkops.com"), timeout=10,
    ) as smtp:
        if os.getenv("SMTP_STARTTLS", "1") == "1":
            smtp.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)
