'''
This module contains the agents' shared ability to access and modify the database.
'''

import os
import typing
import uuid
import json
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
    *, ticket_type: str, email_id: str, sender_email: str, summary: str, raw_email: str, tenant_id: str
) -> Ticket:
    """Create a ticket for human follow-up.

    Args:
        ticket_type: Category for the ticket (e.g., "cancel_order", "complaint").
        email_id: Provider or internal identifier for the inbound email.
        sender_email: Sender address of the inbound email.
        summary: Short summary suitable for a ticket list view.
        raw_email: Full raw email body (stored for audit/debug).
        tenant_id: Tenant identifier.

    Returns:
        The created ticket row.
    """
    
    conn = get_db_conn()
    if not conn:
        logger.error("No DB connection for create_ticket")
        # Return a dummy if DB is down to keep the agent from crashing hard in this demo
        return {
            "ticket_id": str(uuid.uuid4()),
            "ticket_type": ticket_type,
            "status": "open",
            "email_id": email_id,
            "sender_email": sender_email,
            "summary": summary,
            "raw_email": raw_email,
        }

    ticket_id = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tickets (id, tenant_id, email_id, ticket_type, status, sender_email, summary, raw_email)
                VALUES (%s, %s, %s, %s, 'open', %s, %s, %s)
                RETURNING id, status, created_at
                """,
                (ticket_id, tenant_id, email_id, ticket_type, sender_email, summary, raw_email),
            )
            row = cur.fetchone()
            conn.commit()
            if row:
                ticket_id = row[0]
    except Exception as exc:
        logger.error("Failed to insert ticket: %s", exc)
        conn.rollback()
    finally:
        conn.close()

    return {
        "ticket_id": ticket_id,
        "ticket_type": ticket_type,
        "status": "open",
        "email_id": email_id,
        "sender_email": sender_email,
        "summary": summary,
        "raw_email": raw_email,
    }


def create_agent_handoff(
    *,
    tenant_id: str,
    run_id: str | None,
    from_agent_id: str,
    to_agent_id: str,
    kind: str = "handoff",
    message: str | None = None,
    payload: dict[str, typing.Any] | None = None,
) -> None:
    """Queue a handoff or message to another agent via the intercom queue.

    Args:
        tenant_id: Tenant context.
        run_id: Current run identifier (optional).
        from_agent_id: The sending agent.
        to_agent_id: The target agent.
        kind: 'handoff', 'message', 'instruction', etc.
        message: Human-readable instructions or message content.
        payload: Structured context to pass along.
    """
    conn = get_db_conn()
    if not conn:
        logger.error("No DB connection for create_agent_handoff")
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_intercom_queue 
                (tenant_id, run_id, from_agent_id, to_agent_id, kind, message, payload, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued')
                """,
                (
                    tenant_id,
                    run_id,
                    from_agent_id,
                    to_agent_id,
                    kind,
                    message or "",
                    json.dumps(payload or {}),
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.error("Failed to queue handoff: %s", exc)
        conn.rollback()
    finally:
        conn.close()


def process_order_update(
    *,
    tenant_id: str,
    email_id: str,
    summary: str,
    details: dict[str, typing.Any],
) -> None:
    """Log an order update request to the event outbox.

    Args:
        tenant_id: Tenant context.
        email_id: Source email identifier.
        summary: Brief description of the update.
        details: Full details (intent, classification, extracted data).
    """
    conn = get_db_conn()
    if not conn:
        logger.error("No DB connection for process_order_update")
        return

    payload = {
        "email_id": email_id,
        "summary": summary,
        "details": details,
    }

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO event_outbox 
                (tenant_id, event_type, payload, status)
                VALUES (%s, 'update_order', %s, 'queued')
                """,
                (tenant_id, json.dumps(payload)),
            )
            conn.commit()
    except Exception as exc:
        logger.error("Failed to log order update event: %s", exc)
        conn.rollback()
    finally:
        conn.close()