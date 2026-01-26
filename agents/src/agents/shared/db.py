'''
This module contains the agents' shared ability to access and modify the database.
'''

import os
import typing
import uuid
import logging
import psycopg2

logger = logging.getLogger(__name__)

# Simple type definitions to avoid circular dependency on imel.state
class Ticket(typing.TypedDict):
    ticket_id: str
    ticket_type: str
    status: str
    email_id: str
    sender_email: str
    summary: str
    raw_email: str

def get_db_conn():
    """Return a Postgres connection if AGENTS_DB_URL/DATABASE_URL is set.

    Returns:
        A DB connection object, or `None` if not configured or unavailable.
    """

    db_url = os.getenv("AGENTS_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        return psycopg2.connect(db_url)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("DB connection unavailable: %s", exc)
        return None

def create_ticket(
    *, ticket_type: str, email_id: str, sender_email: str, summary: str, raw_email: str
) -> Ticket:
    """Create a ticket for human follow-up.

    TODO(DB): Insert into a real `tickets` table and return the inserted row.

    Args:
        ticket_type: Category for the ticket (e.g., "cancel_order", "complaint").
        email_id: Provider or internal identifier for the inbound email.
        sender_email: Sender address of the inbound email.
        summary: Short summary suitable for a ticket list view.
        raw_email: Full raw email body (stored for audit/debug).

    Returns:
        The created ticket row (currently an in-memory representation).
    """

    # This is intentionally "fake DB" logic to keep the agent flow moving early on.
    return {
        "ticket_id": str(uuid.uuid4()),
        "ticket_type": ticket_type,
        "status": "open",
        "email_id": email_id,
        "sender_email": sender_email,
        "summary": summary,
        "raw_email": raw_email,
    }