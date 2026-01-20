"""Imel agent "nodes" (plain Python functions).

In LangGraph, a "node" is just a function that:
  1) takes a state object (usually a dict-like structure), and
  2) returns an updated state object.

Even if you never use LangGraph, writing your agent logic in this style is useful
because it forces you to keep inputs/outputs explicit and easy to test.
"""

import logging
import typing

from agents.general.imel import policy as imel_policy
from agents.general.imel import prompts as imel_prompts
from agents.general.imel import state as imel_state
from agents.general.imel import tools as imel_tools

logger = logging.getLogger(__name__)


def init_imel_state(
    *,
    email_id: str,
    sender_email: str,
    email_content: str,
    tenant_id: str | None = None,
    tenant_profile: dict[str, typing.Any] | None = None,
) -> imel_state.ImelState:
    """Create the initial Imel state for an email run."""

    return {
        "email_id": email_id,
        "sender_email": sender_email,
        "email_content": email_content,
        "tenant_id": tenant_id,
        "tenant_profile": tenant_profile,  # Loaded from KB/DB
        "classification": None,
        "kb_snippets": None,
        "ticket": None,
        "handoff": None,
        "draft_response": None,
        "action": None,
        "messages": [], # We are not initializing SystemMessages here, as LLM calls should be stateless,
        # SystemPrompt should be injected per LLM call.
    }


def classify_intent_node(state: imel_state.ImelState, *, llm=None) -> imel_state.ImelState:
    """Classify the email into a small set of intents.

    This is intentionally a "small" classification schema so the rest of the
    flow can be deterministic and easy to reason about.
    """

    system_prompt = imel_policy.build_imel_system_prompt(tenant_profile=state.get("tenant_profile"))
    email_prompt = imel_prompts.CLASSIFY_EMAIL_PROMPT.format(
        email_content=state["email_content"],
        sender_email=state["sender_email"],
    )
    classification = imel_tools.classify_email(
        system_prompt=system_prompt,
        email_prompt=email_prompt,
        email_content=state["email_content"],
        sender_email=state["sender_email"],
        llm=llm,
    )

    state["classification"] = classification
    logger.info("Classified email %s as: %s", state["email_id"], classification)
    return state


def company_kb_lookup_node(state: imel_state.ImelState) -> imel_state.ImelState:
    """Fetch relevant company knowledge for generic inquiries.

    This pulls chunks from the tenant_kb_chunks pgvector store (if configured).
    """

    classification = state.get("classification") or {}
    query = " ".join(
        [
            str(classification.get("topic", "")),
            str(classification.get("summary", "")),
            state.get("email_content", ""),
        ]
    ).strip()

    snippets = imel_tools.lookup_company_kb(tenant_id=state.get("tenant_id"), query=query) or []
    state["kb_snippets"] = snippets
    logger.info("KB lookup returned %d snippet(s) for email %s", len(snippets), state["email_id"])
    return state


def draft_inquiry_response_node(state: imel_state.ImelState, *, llm=None) -> imel_state.ImelState:
    """Draft a response for inquiries/general emails.

    Note: This drafts a reply only. Sending the email should be done by your
    orchestrator (services/ai-suite) so you can log/audit/retry centrally.
    """

    system_prompt = imel_policy.build_imel_system_prompt(tenant_profile=state.get("tenant_profile"))
    kb_chunks = state.get("kb_snippets") or []
    kb_snippets = "\n\n".join([chunk.get("content", "") for chunk in kb_chunks if chunk.get("content")])
    draft_prompt = imel_prompts.INQUIRY_DRAFT_REPLY_PROMPT.format(
        email_content=state["email_content"],
        kb_snippets=kb_snippets or "(none)",
    )
    draft = imel_tools.draft_reply(
        system_prompt=system_prompt,
        draft_prompt=draft_prompt,
        classification=state.get("classification"),
        llm=llm,
    )
    state["draft_response"] = draft
    state["action"] = "respond"
    logger.info("Drafted response for email %s (len=%d)", state["email_id"], len(draft))
    return state


def handoff_to_order_manager_node(state: imel_state.ImelState) -> imel_state.ImelState:
    """Create a handoff request for the Order Manager agent.

    IMPORTANT: Imel must NOT access accounts/orders/products DBs. The Order
    Manager agent is the only component allowed to read/write those records.
    """

    classification = state["classification"]
    if not classification:
        raise ValueError("handoff_to_order_manager_node called without classification")

    handoff: imel_state.AgentHandoff = {
        "target_agent": "order_manager",
        "instructions_prompt": imel_prompts.ORDER_MANAGER_HANDOFF_INSTRUCTIONS,
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
    logger.info(
        "Route to Order Manager with this data: %s",
        {
            "email_id": state["email_id"],
            "sender_email": state["sender_email"],
            "intent": classification["intent"],
            "topic": classification.get("topic"),
        },
    )
    return state


def _create_ticket_for_kall(state: imel_state.ImelState, *, ticket_type: str) -> imel_state.Ticket:
    classification = state.get("classification") or {}
    summary = str(classification.get("summary") or "") or state["email_content"][:200]
    return imel_tools.create_ticket_in_db(
        ticket_type=ticket_type,
        email_id=state["email_id"],
        sender_email=state["sender_email"],
        summary=summary,
        raw_email=state["email_content"],
    )


def create_ticket_and_handoff_to_kall_node(state: imel_state.ImelState) -> imel_state.ImelState:
    """Create a ticket and route to Kall for follow-up.

    ALL cancel-order requests and ALL complaints are followed
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

    handoff: imel_state.AgentHandoff = {
        "target_agent": "kall",
        "instructions_prompt": imel_prompts.KALL_HANDOFF_INSTRUCTIONS,
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
    logger.info(
        "Route to Kall with ticket: %s",
        {
            "ticket_id": ticket["ticket_id"],
            "ticket_type": ticket["ticket_type"],
            "email_id": state["email_id"],
            "sender_email": state["sender_email"],
        },
    )
    return state


def archive_node(state: imel_state.ImelState) -> imel_state.ImelState:
    """Mark an email as not requiring a response (e.g. spam).

    TODO(INTEGRATION): Your orchestrator should mark the email as archived/handled
    in the email provider (Gmail/Outlook/etc.).
    """

    state["action"] = "archive"
    logger.info("Archived email %s (no response needed)", state["email_id"])
    return state


def route_by_intent_node(state: imel_state.ImelState, *, llm=None) -> imel_state.ImelState:
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
