"""Email capability (dev/demo).

In a real system this module would integrate with SES/SendGrid/Gmail and own
provider configuration, idempotency, and retries. For now, we keep the external
action intentionally observable and harmless by printing a single line.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FakeEmailSender:
    """A fake email sender for local testing.

    This intentionally does not perform real I/O; it just logs the action so the
    end-to-end agent flow is visible from the CLI.
    """

    def send_email(self, *, email_id: str, to: str, subject: str, body: str) -> None:
        logger.info("Email sent with response: %s", body)

