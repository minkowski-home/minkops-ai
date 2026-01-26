"""Imel agent tools and integrations.

This module keeps external side-effects (actions) here.
Logic for thinking (LLM), data access (DB), and retrieval (KB) has been moved
to `nodes.py` and `agents.shared`.
"""

import logging

logger = logging.getLogger(__name__)


def send_email(*, email_id: str, to: str, subject: str, body: str) -> None:
    """Send an email reply.

    TODO(INTEGRATION): Connect to your email provider (Gmail, SES, SendGrid, etc).
    For now this is a no-op; orchestration can still proceed with draft replies.

    Args:
        email_id: Provider or internal identifier for the inbound email.
        to: Recipient address.
        subject: Email subject line.
        body: Email body content.
    """

    _ = (email_id, to, subject, body)
    # real implementation would go here
    return None
