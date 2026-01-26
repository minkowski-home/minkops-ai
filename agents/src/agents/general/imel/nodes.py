"""Imel agent "nodes" (plain Python functions).

In LangGraph, a "node" is just a function that:
  1) takes a state object (usually a dict-like structure), and
  2) returns an updated state object.

Even if you never use LangGraph, writing your agent logic in this style is useful
because it forces you to keep inputs/outputs explicit and easy to test.
"""

import logging
import typing

# Agent-specific imports
from agents.general.imel import policy as imel_policy
from agents.general.imel import prompts as imel_prompts
from agents.general.imel import state as imel_state

# Shared Capability imports
from agents.shared import db as shared_db
from agents.shared import kb as shared_kb
from agents.shared import utils as shared_utils
from agents.shared import clients as shared_clients

# Tools (only for Actions)
from agents.general.imel import tools as imel_tools

import langchain_core.messages as lc_messages

logger = logging.getLogger(__name__)


# --- Internal Helper Functions (LLM Logic) ---

def _classify_email_heuristic(*, email_content: str, sender_email: str) -> imel_state.EmailClassification:
    """A tiny, dependency-free classifier for demos."""
    text = f"{sender_email}\n{email_content}".lower()

    # Very rough signals.
    is_spam = any(s in text for s in ["unsubscribe", "win money", "crypto", "airdrop", "free gift", "click here"])
    wants_cancel = any(s in text for s in ["cancel", "cancellation", "stop my order"])
    is_complaint = any(s in text for s in ["complaint", "not happy", "angry", "terrible", "refund", "chargeback"])
    order_related = any(s in text for s in ["order", "tracking", "shipment", "shipping", "invoice", "account"])
    wants_update = any(s in text for s in ["change", "update", "edit", "modify"]) and order_related

    if is_spam:
        intent = "spam"
    elif wants_cancel:
        intent = "cancel_order"
    elif is_complaint:
        intent = "complaint"
    elif wants_update:
        intent = "update_order"
    elif order_related:
        intent = "order_or_account_details"
    else:
        intent = "inquiry"

    # Human escalation triggers (demo-level heuristics).
    human_required = any(s in text for s in ["lawyer", "sue", "threat", "harass", "fraud", "police"])
    urgency = "human_intervention_required" if human_required else ("medium" if intent in {"complaint", "cancel_order"} else "low")

    topic = "order/account" if intent in {"order_or_account_details", "update_order", "cancel_order"} else (
        "complaint" if intent == "complaint" else "general"
    )
    summary = (email_content.strip().replace("\n", " ")[:160] + ("…" if len(email_content.strip()) > 160 else "")).strip()

    return {
        "intent": intent,  # type: ignore[literal-required]
        "urgency": urgency,  # type: ignore[literal-required]
        "topic": topic,
        "summary": summary or "No content.",
        "is_human_intervention_required": bool(human_required),
    }

def _coerce_email_classification(payload: dict[str, typing.Any]) -> imel_state.EmailClassification:
    """Coerce untrusted JSON into an `EmailClassification` shape."""
    intent = payload.get("intent", "other")
    urgency = payload.get("urgency", "low")
    topic = payload.get("topic", "")
    summary = payload.get("summary", "")
    is_human = bool(payload.get("is_human_intervention_required", False))

    allowed_intents = {
        "inquiry", "complaint", "feedback", "order_or_account_details",
        "update_order", "cancel_order", "other", "spam"
    }
    if intent not in allowed_intents:
        intent = "other"

    allowed_urgency = {"low", "medium", "human_intervention_required"}
    if urgency not in allowed_urgency:
        urgency = "low"

    if urgency == "human_intervention_required":
        is_human = True

    return {
        "intent": intent,  # type: ignore[literal-required]
        "urgency": urgency,  # type: ignore[literal-required]
        "topic": str(topic),
        "summary": str(summary),
        "is_human_intervention_required": is_human,
    }

def _classify_email(
    *, system_prompt: str, email_prompt: str, email_content: str, sender_email: str, llm=None
) -> imel_state.EmailClassification:
    """Classify using an LLM if provided; otherwise use heuristics."""
    if llm is None:
        return _classify_email_heuristic(email_content=email_content, sender_email=sender_email)
    
    # Use generic LLM client wrapper
    llm = llm or shared_clients.get_chat_model()
    result = llm.invoke(
        [lc_messages.SystemMessage(content=system_prompt), lc_messages.HumanMessage(content=email_prompt)]
    )
    # Use shared utility for JSON extraction
    payload = shared_utils.safe_json_extract(getattr(result, "content", str(result)))
    return _coerce_email_classification(payload)

def _draft_reply(
    *, system_prompt: str, draft_prompt: str, classification: imel_state.EmailClassification | None, llm=None
) -> str:
    """Draft using an LLM if provided; otherwise use a simple template."""
    if llm is not None:
        llm = llm or shared_clients.get_chat_model()
        result = llm.invoke(
            [lc_messages.SystemMessage(content=system_prompt), lc_messages.HumanMessage(content=draft_prompt)]
        )
        return (getattr(result, "content", str(result)) or "").strip()

    # Demo fallback
    topic = (classification or {}).get("topic", "your message")
    return "\n".join(
        [
            "Thanks for reaching out.",
            "",
            f"I received your email about {topic}.",
            "To help you quickly, could you share any relevant details (order number, account email, dates) if applicable?",
            "",
            "Best,",
            "Imel (Nathan)",
        ]
    ).strip()


# --- Public Nodes ---

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
        "tenant_profile": tenant_profile,
        "classification": None,
        "kb_snippets": None,
        "ticket": None,
        "handoff": None,
        "draft_response": None,
        "action": None,
        "messages": [],
    }


def classify_intent_node(state: imel_state.ImelState, *, llm=None) -> imel_state.ImelState:
    """Classify the email into a small set of intents."""
    system_prompt = imel_policy.build_imel_system_prompt(tenant_profile=state.get("tenant_profile"))
    email_prompt = imel_prompts.CLASSIFY_EMAIL_PROMPT.format(
        email_content=state["email_content"],
        sender_email=state["sender_email"],
    )
    
    classification = _classify_email(
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
    """Fetch relevant company knowledge for generic inquiries."""
    classification = state.get("classification") or {}
    query = " ".join(
        [
            str(classification.get("topic", "")),
            str(classification.get("summary", "")),
            state.get("email_content", ""),
        ]
    ).strip()

    # Use Shared Capability
    # Cast/Transform KBChunk if necessary or assume compatible TypedDicts
    # Note: agents.shared.kb.KBChunk is compatible with imel.state.KBChunk
    snippets = shared_kb.lookup_company_kb(tenant_id=state.get("tenant_id"), query=query) or []
    
    state["kb_snippets"] = typing.cast(list[imel_state.KBChunk], snippets)
    logger.info("KB lookup returned %d snippet(s) for email %s", len(snippets), state["email_id"])
    return state


def draft_inquiry_response_node(state: imel_state.ImelState, *, llm=None) -> imel_state.ImelState:
    """Draft a response for inquiries/general emails."""
    system_prompt = imel_policy.build_imel_system_prompt(tenant_profile=state.get("tenant_profile"))
    kb_chunks = state.get("kb_snippets") or []
    kb_snippets = "\n\n".join([chunk.get("content", "") for chunk in kb_chunks if chunk.get("content")])
    draft_prompt = imel_prompts.INQUIRY_DRAFT_REPLY_PROMPT.format(
        email_content=state["email_content"],
        kb_snippets=kb_snippets or "(none)",
    )
    
    draft = _draft_reply(
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
    """Create a handoff request for the Order Manager agent."""
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


def create_ticket_and_handoff_to_kall_node(state: imel_state.ImelState) -> imel_state.ImelState:
    """Create a ticket and route to Kall for follow-up."""
    classification = state["classification"]
    if not classification:
        raise ValueError("create_ticket_and_handoff_to_kall_node called without classification")

    if classification["intent"] == "cancel_order":
        ticket_type = "cancel_order"
    else:
        ticket_type = "complaint"

    # Use Shared Capability
    summary = str(classification.get("summary") or "") or state["email_content"][:200]
    ticket = shared_db.create_ticket(
        ticket_type=ticket_type,
        email_id=state["email_id"],
        sender_email=state["sender_email"],
        summary=summary,
        raw_email=state["email_content"],
    )

    handoff: imel_state.AgentHandoff = {
        "target_agent": "kall",
        "instructions_prompt": imel_prompts.KALL_HANDOFF_INSTRUCTIONS,
        "context": {
            "ticket": typing.cast(imel_state.Ticket, ticket),
            "email_id": state["email_id"],
            "sender_email": state["sender_email"],
            "email_content": state["email_content"],
            "classification": classification,
            "tenant_id": state.get("tenant_id"),
        },
    }

    state["ticket"] = typing.cast(imel_state.Ticket, ticket)
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
    """Mark an email as not requiring a response (e.g. spam)."""
    state["action"] = "archive"
    logger.info("Archived email %s (no response needed)", state["email_id"])
    return state


def route_by_intent_node(state: imel_state.ImelState, *, llm=None) -> imel_state.ImelState:
    """Route the email based on classification."""
    classification = state.get("classification")
    if not classification:
        raise ValueError("route_by_intent_node called without classification")

    if classification.get("is_human_intervention_required"):
        return create_ticket_and_handoff_to_kall_node(state)

    intent = classification["intent"]

    if intent in {"order_or_account_details", "update_order"}:
        return handoff_to_order_manager_node(state)

    if intent in {"cancel_order", "complaint"}:
        return create_ticket_and_handoff_to_kall_node(state)

    if intent == "spam":
        return archive_node(state)

    state = company_kb_lookup_node(state)
    return draft_inquiry_response_node(state, llm=llm)
