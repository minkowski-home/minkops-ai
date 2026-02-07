"""Kall agent nodes.

Kall is a human-style escalation resolver. For now, the flow is intentionally
minimal and deterministic so runtime wiring stays easy to verify.
"""

from __future__ import annotations

import logging

from agents.general.kall import state as kall_state
from agents.general.kall import tools as kall_tools

logger = logging.getLogger(__name__)


def init_kall_state(*, tenant_id: str, ticket_id: str, sender_email: str | None = None) -> kall_state.KallState:
    """Initialize state for one Kall run."""

    return {
        "tenant_id": tenant_id,
        "ticket_id": ticket_id,
        "sender_email": sender_email,
        "ticket": None,
        "resolution_notes": None,
        "outbound_message": None,
        "action": None,
    }


def load_ticket_node(state: kall_state.KallState, *, tools: kall_tools.KallTools) -> kall_state.KallState:
    """Load the target ticket from storage."""

    ticket = tools.get_ticket(ticket_id=state["ticket_id"], tenant_id=state["tenant_id"])
    state["ticket"] = ticket
    if ticket is None:
        state["action"] = "no_ticket"
        state["resolution_notes"] = f"Ticket {state['ticket_id']} not found."
        logger.info("Kall could not find ticket=%s tenant=%s", state["ticket_id"], state["tenant_id"])
    else:
        logger.info("Kall loaded ticket=%s type=%s", ticket["ticket_id"], ticket["ticket_type"])
    return state


def resolve_ticket_node(state: kall_state.KallState, *, tools: kall_tools.KallTools) -> kall_state.KallState:
    """Resolve the ticket and optionally prepare a customer-facing response."""

    ticket = state.get("ticket")
    if ticket is None:
        state["outbound_message"] = (
            "We could not locate your support ticket yet. "
            "Please reply with your original request details so we can help quickly."
        )
        # If sender exists we can still notify; otherwise leave as no_ticket.
        if state.get("sender_email"):
            state["action"] = "respond"
        return state

    # Kall closes the ticket after resolution in this MVP flow.
    tools.update_ticket_status(ticket_id=ticket["ticket_id"], tenant_id=state["tenant_id"], status="closed")

    if ticket["ticket_type"] == "cancel_order":
        resolution_message = (
            "Your cancellation request has been processed and marked complete. "
            "If you need a follow-up receipt, reply to this email."
        )
    else:
        resolution_message = (
            "Thank you for reporting this issue. We investigated and applied a resolution. "
            "If anything still looks wrong, reply and we will reopen immediately."
        )

    state["resolution_notes"] = resolution_message
    state["outbound_message"] = resolution_message
    state["action"] = "respond" if state.get("sender_email") else "resolved"

    # Keep inter-agent observability: notify Imel that Kall completed resolution.
    tools.create_agent_handoff(
        tenant_id=state["tenant_id"],
        run_id=None,
        from_agent_id="kall",
        to_agent_id="imel",
        kind="message",
        message=f"Resolved ticket {ticket['ticket_id']}",
        payload={"ticket_id": ticket["ticket_id"], "status": "closed"},
    )

    logger.info("Kall resolved ticket=%s action=%s", ticket["ticket_id"], state["action"])
    return state
