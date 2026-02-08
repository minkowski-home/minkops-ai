"""Imel agent "nodes" (plain Python functions).

In LangGraph, a "node" is just a function that:
  1) takes a state object (usually a dict-like structure), and
  2) returns an updated state object.

Even if you never use LangGraph, writing your agent logic in this style is useful
because it forces you to keep inputs/outputs explicit and easy to test.
"""

import json
import logging
import re
import typing

# Agent-specific imports
from agents.general.imel import policy as imel_policy
from agents.general.imel import prompts as imel_prompts
from agents.general.imel import state as imel_state
from agents.general.imel import tools as imel_tools

from typing import Literal
from langgraph.types import Command

logger = logging.getLogger(__name__)


# --- Public Nodes ---

def init_imel_state(
    *,
    email_id: str,
    sender_email: str,
    email_content: str,
    tenant_id: str | None = None,
    tenant_profile: imel_state.TenantProfile | None = None,
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
        "messages": [], # No system prompt here, it should be added during runtime per run
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


def company_kb_lookup_node(
    state: imel_state.ImelState, *, tools: imel_tools.ImelTools
) -> Command[Literal["draft_inquiry_response"]]:
    """Fetch relevant company knowledge for generic inquiries.
    
    Returns:
        Command(goto="draft_inquiry_response"): Always proceeds to drafting.
    """
    classification = state.get("classification") or {}
    query = " ".join(
        [
            str(classification.get("topic", "")),
            str(classification.get("summary", "")),
            state.get("email_content", ""),
        ]
    ).strip()

    snippets = tools.lookup_company_kb(tenant_id=state.get("tenant_id"), query=query) or []
    
    state["kb_snippets"] = snippets
    logger.info("KB lookup returned %d snippet(s) for email %s", len(snippets), state["email_id"])
    
    return Command(
        update={"kb_snippets": state["kb_snippets"]},
        goto="draft_inquiry_response"
    )


def draft_inquiry_response_node(state: imel_state.ImelState, *, llm=None) -> Command[Literal["__end__"]]:
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
    
    return Command(
        update={"draft_response": draft, "action": "respond"},
        goto="__end__"
    )


def process_order_node(
    state: imel_state.ImelState, *, tools: imel_tools.ImelTools
) -> Command[Literal["draft_inquiry_response"]]:
    """Log an order update request to be handled asynchronously."""
    classification = state["classification"]
    if not classification:
        raise ValueError("process_order_node called without classification")

    summary = str(classification.get("summary") or "")
    
    # Service-layer tool implementation owns DB transactions/outbox semantics.
    tools.process_order_update(
        tenant_id=state.get("tenant_id", "default"),
        email_id=state["email_id"],
        summary=summary,
        details=classification
    )
    
    state["action"] = "process_order"
    logger.info("Logged order update event for email %s", state["email_id"])
    
    # After processing, we draft a response confirming receipt
    return Command(
        update={"action": "process_order"},
        goto="draft_inquiry_response"
    )


def create_ticket_and_handoff_to_kall_node(
    state: imel_state.ImelState, *, tools: imel_tools.ImelTools
) -> Command[Literal["__end__"]]:
    """Create a ticket and route to Kall for follow-up.
       Creating a ticket and handing off to call happen transactionally (not by design, just by coincidence here),
       both are triggered when a cancel order request arrives. Later, we shall create separate functions for:
       1. Creating ticket (as a graph "node", logically different from the create ticket "tool",
       2. Handing off (not just to call, but a general function to hand-off to any agent decided by LLM (another LLM node might be needed)
    """
    classification = state["classification"]
    if not classification:
        raise ValueError("create_ticket_and_handoff_to_kall_node called without classification")

    if classification["intent"] == "cancel_order":
        ticket_type = "cancel_order"
    else:
        ticket_type = "complaint"

    summary = str(classification.get("summary") or "") or state["email_content"][:200]
    
    # 1. Persist Ticket (service layer owns DB write semantics).
    ticket = tools.create_ticket(
        ticket_type=ticket_type,
        email_id=state["email_id"],
        sender_email=state["sender_email"],
        summary=summary,
        raw_email=state["email_content"],
        tenant_id=state.get("tenant_id", "default")
    )

    # 2. Queue Handoff in Intercom Queue (service layer owns DB write semantics).
    tools.create_agent_handoff(
        tenant_id=state.get("tenant_id", "default"),
        run_id=None, # In real app, pass current run_id
        from_agent_id="imel",
        to_agent_id="kall",
        kind="handoff",
        message=f"Please handle {ticket_type} ticket {ticket['ticket_id']}",
        payload={
            "ticket_id": ticket["ticket_id"],
            "classification": classification
        }
    )

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
    logger.info("Route to Kall with ticket: %s", ticket["ticket_id"])
    
    return Command(
        update={"ticket": state["ticket"], "handoff": handoff, "action": "handoff"},
        goto="__end__"
    )


def archive_node(state: imel_state.ImelState) -> Command[Literal["__end__"]]:
    """Mark an email as not requiring a response (e.g. spam)."""
    state["action"] = "archive"
    logger.info("Archived email %s (no response needed)", state["email_id"])
    return Command(
        update={"action": "archive"},
        goto="__end__"
    )


def route_by_intent_node(state: imel_state.ImelState, *, llm=None) -> Command[Literal["process_order", "create_ticket_and_handoff_to_kall", "archive", "company_kb_lookup"]]:
    """Route the email based on classification using LangGraph Command."""
    classification = state.get("classification")
    if not classification:
        raise ValueError("route_by_intent_node called without classification")

    if classification.get("is_human_intervention_required"):
        return Command(goto="create_ticket_and_handoff_to_kall")

    intent = classification["intent"]

    if intent in {"order_or_account_details", "update_order"}:
        return Command(goto="process_order")

    if intent in {"cancel_order", "complaint"}:
         return Command(goto="create_ticket_and_handoff_to_kall")

    if intent == "spam":
         return Command(goto="archive")

    # Everything else: use the company knowledge base and respond.
    return Command(goto="company_kb_lookup")


def _extract_text(value: typing.Any) -> str:
    """Normalize provider responses into plain text."""

    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Some chat providers return a list of content blocks.
        return "".join(str(part) for part in content)
    return str(value) if value is not None else ""


def _extract_json_object(text: str) -> dict[str, typing.Any] | None:
    """Extract and parse the first JSON object from free-form model output."""

    text = text.strip()
    if not text:
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _fallback_classification(*, email_content: str) -> imel_state.EmailClassification:
    """Deterministic classifier used when no model is available or parsing fails."""

    content = email_content.lower()

    if any(token in content for token in ("unsubscribe", "winner", "lottery", "bitcoin", "free money")):
        intent = "spam"
    elif "cancel" in content:
        intent = "cancel_order"
    elif any(token in content for token in ("problem", "issue", "broken", "angry", "complaint")):
        intent = "complaint"
    elif any(token in content for token in ("update", "status", "track", "order")):
        intent = "update_order"
    elif any(token in content for token in ("account", "invoice", "billing", "plan")):
        intent = "order_or_account_details"
    elif any(token in content for token in ("thanks", "great", "love")):
        intent = "feedback"
    else:
        intent = "inquiry"

    is_human = intent in {"complaint", "cancel_order"}
    urgency: typing.Literal["low", "medium", "human_intervention_required"] = (
        "human_intervention_required" if is_human else "medium"
    )

    return {
        "intent": typing.cast(
            typing.Literal[
                "inquiry",
                "complaint",
                "feedback",
                "order_or_account_details",
                "update_order",
                "cancel_order",
                "other",
                "spam",
            ],
            intent,
        ),
        "urgency": urgency,
        "topic": "customer_email",
        "summary": email_content.strip()[:200],
        "is_human_intervention_required": is_human,
    }


def _normalize_classification(raw: dict[str, typing.Any], *, email_content: str) -> imel_state.EmailClassification:
    """Validate/coerce raw model output into the agent's classification schema."""

    allowed_intents = {
        "inquiry",
        "complaint",
        "feedback",
        "order_or_account_details",
        "update_order",
        "cancel_order",
        "other",
        "spam",
    }
    intent_raw = str(raw.get("intent") or "").strip().lower()
    intent = intent_raw if intent_raw in allowed_intents else "other"

    urgency_raw = str(raw.get("urgency") or "").strip().lower()
    urgency: typing.Literal["low", "medium", "human_intervention_required"]
    if urgency_raw in {"low", "medium", "human_intervention_required"}:
        urgency = typing.cast(typing.Literal["low", "medium", "human_intervention_required"], urgency_raw)
    else:
        urgency = "human_intervention_required" if intent in {"complaint", "cancel_order"} else "medium"

    topic = str(raw.get("topic") or "customer_email").strip() or "customer_email"
    summary = str(raw.get("summary") or "").strip() or email_content.strip()[:200]

    human_flag = raw.get("is_human_intervention_required")
    if isinstance(human_flag, bool):
        is_human = human_flag
    else:
        is_human = urgency == "human_intervention_required" or intent in {"complaint", "cancel_order"}

    return {
        "intent": typing.cast(
            typing.Literal[
                "inquiry",
                "complaint",
                "feedback",
                "order_or_account_details",
                "update_order",
                "cancel_order",
                "other",
                "spam",
            ],
            intent,
        ),
        "urgency": urgency,
        "topic": topic,
        "summary": summary,
        "is_human_intervention_required": is_human,
    }


def _classify_email(
    *,
    system_prompt: str,
    email_prompt: str,
    email_content: str,
    sender_email: str,
    llm=None,
) -> imel_state.EmailClassification:
    """Return a schema-safe classification, with deterministic fallback."""

    if llm is None:
        return _fallback_classification(email_content=email_content)

    try:
        response = llm.invoke(f"{system_prompt}\n\n{email_prompt}")
        parsed = _extract_json_object(_extract_text(response))
        if parsed:
            return _normalize_classification(parsed, email_content=email_content)
    except Exception as exc:
        logger.warning("LLM classification failed for %s: %s", sender_email, exc)

    return _fallback_classification(email_content=email_content)


def _fallback_draft(*, classification: imel_state.EmailClassification | None) -> str:
    """Deterministic reply when no model is available."""

    intent = (classification or {}).get("intent")
    if intent in {"update_order", "order_or_account_details"}:
        return (
            "Thanks for reaching out. We received your request and queued an order/account update. "
            "We will follow up with details shortly."
        )
    if intent in {"cancel_order", "complaint"}:
        return (
            "Thanks for your message. We have opened a support ticket and escalated this to a specialist. "
            "You will receive a follow-up shortly."
        )
    if intent == "spam":
        return "Thanks for contacting us."
    return (
        "Thanks for your email. We received your request and will follow up shortly "
        "with the most accurate next steps."
    )


def _draft_reply(
    *,
    system_prompt: str,
    draft_prompt: str,
    classification: imel_state.EmailClassification | None,
    llm=None,
) -> str:
    """Generate a reply draft with LLM when available, fallback otherwise."""

    if llm is None:
        return _fallback_draft(classification=classification)

    try:
        response = llm.invoke(f"{system_prompt}\n\n{draft_prompt}")
        content = _extract_text(response).strip()
        if content:
            return content
    except Exception as exc:
        logger.warning("LLM drafting failed: %s", exc)

    return _fallback_draft(classification=classification)
