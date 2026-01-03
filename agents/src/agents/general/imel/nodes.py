"""Imel agent "nodes" (plain Python functions).

In LangGraph, a "node" is just a function that:
  1) takes a state object (usually a dict-like structure), and
  2) returns an updated state object.

Even if you never use LangGraph, writing your agent logic in this style is useful
because it forces you to keep inputs/outputs explicit and easy to test.
"""

from __future__ import annotations

from typing import Any

from agents.general.imel.policy import build_imel_system_prompt
from agents.general.imel.prompts import (
    CLASSIFY_EMAIL_PROMPT,
    INQUIRY_DRAFT_REPLY_PROMPT,
    KALL_HANDOFF_INSTRUCTIONS,
    ORDER_MANAGER_HANDOFF_INSTRUCTIONS,
)
from agents.general.imel.state import AgentHandoff, ImelState, Ticket
from agents.general.imel.tools import (
    classify_email_via_llm,
    create_ticket_in_db,
    draft_reply_via_llm,
    lookup_company_kb,
)


def init_imel_state(
    *,
    email_id: str,
    sender_email: str,
    email_content: str,
    tenant_id: str | None = None,
    tenant_brand: dict[str, Any] | None = None,
) -> ImelState:
    """Create the initial Imel state for an email run."""

    return {
        "email_id": email_id,
        "sender_email": sender_email,
        "email_content": email_content,
        "tenant_id": tenant_id,
        "tenant_brand": tenant_brand,  # TODO(DB): load from tenant config table
        "classification": None,
        "kb_snippets": None,
        "ticket": None,
        "handoff": None,
        "draft_response": None,
        "action": None,
        "messages": [],
    }


def classify_intent_node(state: ImelState, *, llm=None) -> ImelState:
    """Classify the email into a small set of intents.

    This is intentionally a "small" classification schema so the rest of the
    flow can be deterministic and easy to reason about.
    """

    system_prompt = build_imel_system_prompt(tenant_brand=state.get("tenant_brand"))
    email_prompt = CLASSIFY_EMAIL_PROMPT.format(
        email_content=state["email_content"],
        sender_email=state["sender_email"],
    )
    classification = classify_email_via_llm(system_prompt=system_prompt, email_prompt=email_prompt, llm=llm)

    state["classification"] = classification
    return state


def company_kb_lookup_node(state: ImelState) -> ImelState:
    """Fetch relevant company knowledge for generic inquiries.

    This is a placeholder; it will later call your retrieval system (vector DB,
    Postgres, etc.) using the tenant's knowledge sources.
    """

    classification = state.get("classification") or {}
    query = " ".join(
        [
            str(classification.get("topic", "")),
            str(classification.get("summary", "")),
            state.get("email_content", ""),
        ]
    ).strip()

    snippets = lookup_company_kb(tenant_id=state.get("tenant_id"), query=query)
    state["kb_snippets"] = snippets
    return state


def draft_inquiry_response_node(state: ImelState, *, llm=None) -> ImelState:
    """Draft a response for inquiries/general emails.

    Note: This drafts a reply only. Sending the email should be done by your
    orchestrator (services/ai-suite) so you can log/audit/retry centrally.
    """

    system_prompt = build_imel_system_prompt(tenant_brand=state.get("tenant_brand"))
    kb_snippets = "\n\n".join(state.get("kb_snippets") or [])
    draft_prompt = INQUIRY_DRAFT_REPLY_PROMPT.format(
        email_content=state["email_content"],
        kb_snippets=kb_snippets or "(none)",
    )
    draft = draft_reply_via_llm(system_prompt=system_prompt, draft_prompt=draft_prompt, llm=llm)
    state["draft_response"] = draft
    state["action"] = "respond"
    return state


def handoff_to_order_manager_node(state: ImelState) -> ImelState:
    """Create a handoff request for the Order Manager agent.

    IMPORTANT: Imel must NOT access accounts/orders/products DBs. The Order
    Manager agent is the only component allowed to read/write those records.
    """

    classification = state["classification"]
    if not classification:
        raise ValueError("handoff_to_order_manager_node called without classification")

    handoff: AgentHandoff = {
        "target_agent": "order_manager",
        "instructions_prompt": ORDER_MANAGER_HANDOFF_INSTRUCTIONS,
        "context": {
            "email_id": state["email_id"],
            "sender_email": state["sender_email"],
            "email_content": state["email_content"],
            "classification": classification,
            # TODO(DB): order manager should look up customer/order/account records here
            # using tenant_id + sender_email + any order identifiers mentioned in the email.
            "tenant_id": state.get("tenant_id"),
        },
    }
    state["handoff"] = handoff
    state["action"] = "handoff"
    return state


def _create_ticket_for_kall(state: ImelState, *, ticket_type: str) -> Ticket:
    classification = state.get("classification") or {}
    summary = str(classification.get("summary") or "") or state["email_content"][:200]
    return create_ticket_in_db(
        ticket_type=ticket_type,
        email_id=state["email_id"],
        sender_email=state["sender_email"],
        summary=summary,
        raw_email=state["email_content"],
    )


def create_ticket_and_handoff_to_kall_node(state: ImelState) -> ImelState:
    """Create a ticket and route to Kall for follow-up.

    Per your flowchart: ALL cancel-order requests and ALL complaints are followed
    up by Kall (callback agent).
    """

    classification = state["classification"]
    if not classification:
        raise ValueError("create_ticket_and_handoff_to_kall_node called without classification")

    if classification["intent"] == "cancel_order":
        ticket_type = "cancel_order"
    else:
        # Complaint (and any other high-touch case you decide later).
        ticket_type = "complaint"

    ticket = _create_ticket_for_kall(state, ticket_type=ticket_type)

    # TODO(DB): If you want separate "complaints" logging, add a complaints table
    # and write a row here when ticket_type == "complaint".

    handoff: AgentHandoff = {
        "target_agent": "kall",
        "instructions_prompt": KALL_HANDOFF_INSTRUCTIONS,
        "context": {
            "ticket": ticket,
            "email_id": state["email_id"],
            "sender_email": state["sender_email"],
            "email_content": state["email_content"],
            "classification": classification,
            "tenant_id": state.get("tenant_id"),
        },
    }

    state["ticket"] = ticket
    state["handoff"] = handoff
    state["action"] = "handoff"
    return state


def archive_node(state: ImelState) -> ImelState:
    """Mark an email as not requiring a response (e.g. spam).

    TODO(INTEGRATION): Your orchestrator should mark the email as archived/handled
    in the email provider (Gmail/Outlook/etc.).
    """

    state["action"] = "archive"
    return state


def route_by_intent_node(state: ImelState, *, llm=None) -> ImelState:
    """Route the email based on classification.

    This matches your flowchart:
    - inquiry/general -> Company KB -> Respond
    - update/order/account details -> Order Manager (handoff)
    - cancel order -> ticket + Kall (handoff)
    - complaint -> ticket/log + Kall (handoff)
    - spam -> archive
    """

    classification = state.get("classification")
    if not classification:
        raise ValueError("route_by_intent_node called without classification")

    # If the model says "human required", treat it as a Kall follow-up.
    if classification.get("is_human_intervention_required"):
        return create_ticket_and_handoff_to_kall_node(state)

    intent = classification["intent"]

    if intent in {"order_or_account_details", "update_order"}:
        return handoff_to_order_manager_node(state)

    if intent in {"cancel_order", "complaint"}:
        return create_ticket_and_handoff_to_kall_node(state)

    if intent == "spam":
        return archive_node(state)

    # Everything else: use the company knowledge base and respond.
    state = company_kb_lookup_node(state)
    return draft_inquiry_response_node(state, llm=llm)

