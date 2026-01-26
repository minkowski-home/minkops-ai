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

from typing import Literal
from langgraph.types import Command

# ... (Previous imports remain same) ...
# Shared Capability imports
from agents.shared import db as shared_db
from agents.shared import kb as shared_kb
from agents.shared import utils as shared_utils
from agents.shared import clients as shared_clients

# Tools (only for Actions)

import langchain_core.messages as lc_messages

logger = logging.getLogger(__name__)


# --- Internal Helper Functions (LLM Logic) ---
# ... (Internal helpers remain same) ...

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


def company_kb_lookup_node(state: imel_state.ImelState) -> Command[Literal["draft_inquiry_response"]]:
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

    snippets = shared_kb.lookup_company_kb(tenant_id=state.get("tenant_id"), query=query) or []
    
    state["kb_snippets"] = typing.cast(list[imel_state.KBChunk], snippets)
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


def process_order_node(state: imel_state.ImelState) -> Command[Literal["draft_inquiry_response"]]:
    """Log an order update request to be handled asynchronously."""
    classification = state["classification"]
    if not classification:
        raise ValueError("process_order_node called without classification")

    summary = str(classification.get("summary") or "")
    
    # Use Shared Capability to log event
    shared_db.process_order_update(
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


def create_ticket_and_handoff_to_kall_node(state: imel_state.ImelState) -> Command[Literal["__end__"]]:
    """Create a ticket and route to Kall for follow-up."""
    classification = state["classification"]
    if not classification:
        raise ValueError("create_ticket_and_handoff_to_kall_node called without classification")

    if classification["intent"] == "cancel_order":
        ticket_type = "cancel_order"
    else:
        ticket_type = "complaint"

    summary = str(classification.get("summary") or "") or state["email_content"][:200]
    
    # 1. Create real Ticket in DB
    ticket = shared_db.create_ticket(
        ticket_type=ticket_type,
        email_id=state["email_id"],
        sender_email=state["sender_email"],
        summary=summary,
        raw_email=state["email_content"],
        tenant_id=state.get("tenant_id", "default")
    )

    # 2. Queue Handoff in Intercom Queue
    shared_db.create_agent_handoff(
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
