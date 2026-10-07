"""Production relay greeting and certificate validation are explicit."""

from email.message import EmailMessage
import os
import unittest
from unittest.mock import patch

from minkops_connectors.email import send_email


class EmailTests(unittest.TestCase):
    def test_relay_uses_public_hostname_and_verified_tls(self):
        message = EmailMessage()
        message["To"] = "admin@example.com"
        message.set_content("verification")
        with patch.dict(os.environ, {"SMTP_HOST": "smtp-relay.gmail.com", "SMTP_PORT": "587",
                                     "SMTP_USER": "relay-user", "SMTP_PASSWORD": "secret",
                                     "SMTP_STARTTLS": "1", "SMTP_EHLO_HOST": "minkops.com"}), patch(
            "minkops_connectors.email.smtplib.SMTP"
        ) as smtp:
            send_email(message)
        smtp.assert_called_once_with("smtp-relay.gmail.com", 587, local_hostname="minkops.com", timeout=10)
        client = smtp.return_value.__enter__.return_value
        context = client.starttls.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        client.login.assert_called_once_with("relay-user", "secret")
        client.send_message.assert_called_once_with(message)
