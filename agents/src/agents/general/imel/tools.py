from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from agents.general.imel.state import EmailClassification, Ticket


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def create_ticket_in_db(*, ticket_type: str, email_id: str, sender_email: str, summary: str, raw_email: str) -> Ticket:
    """Create a ticket for human follow-up.

    TODO(DB): Insert into a real `tickets` table and return the inserted row.
    Suggested columns: ticket_id (uuid), type, status, email_id, sender_email,
    summary, raw_email, created_at, updated_at.
    """

    # This is intentionally "fake DB" logic to keep the agent flow moving early on.
    # Your orchestrator will later replace this with a database insert.
    return {
        "ticket_id": str(uuid.uuid4()),
        "ticket_type": ticket_type,  # "cancel_order" | "complaint"
        "status": "open",
        "email_id": email_id,
        "sender_email": sender_email,
        "summary": summary,
        "raw_email": raw_email,
    }


def lookup_company_kb(*, tenant_id: str | None, query: str) -> list[str]:
    """Return knowledge-base snippets relevant to the query.

    TODO(DB): Use your tenant's knowledge sources (documents, FAQs, policies)
    stored in a vector DB / Postgres / files, then return top-k snippets.
    """

    _ = (tenant_id, query)
    return []


def _safe_json_extract(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from an LLM response."""

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Common pattern: the model wraps JSON in markdown fences.
        if "```" in text:
            stripped = text.replace("```json", "```").strip()
            parts = stripped.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("{") and part.endswith("}"):
                    return json.loads(part)
        raise


def coerce_email_classification(payload: dict[str, Any]) -> EmailClassification:
    """Coerce untrusted JSON into an `EmailClassification` shape.

    We keep validation light here to avoid blocking iteration. In production
    you’d typically use Pydantic for strict validation + better error messages.
    """

    intent = payload.get("intent", "other")
    urgency = payload.get("urgency", "low")
    topic = payload.get("topic", "")
    summary = payload.get("summary", "")
    is_human = bool(payload.get("is_human_intervention_required", False))

    # If the model outputs an unknown value, force a safe fallback.
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


def get_chat_model(*, model: str = "gemma3:4b", temperature: float = 0.3):
    """Create a chat model instance.

    This is kept in `tools.py` so the rest of the agent code can be plain Python.
    The only LangChain-specific part is hidden behind this constructor.
    """

    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, temperature=temperature)


def classify_email_via_llm(*, system_prompt: str, email_prompt: str, llm=None) -> EmailClassification:
    """Call an LLM to classify an email and return structured JSON."""

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = llm or get_chat_model()
    result = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=email_prompt)])
    payload = _safe_json_extract(getattr(result, "content", str(result)))
    return coerce_email_classification(payload)


def draft_reply_via_llm(*, system_prompt: str, draft_prompt: str, llm=None) -> str:
    """Call an LLM to draft a response email."""

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = llm or get_chat_model()
    result = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=draft_prompt)])
    return (getattr(result, "content", str(result)) or "").strip()


def send_email(*, email_id: str, to: str, subject: str, body: str) -> None:
    """Send an email reply.

    TODO(INTEGRATION): Connect to your email provider (Gmail, SES, SendGrid, etc).
    For now this is a no-op; orchestration can still proceed with draft replies.
    """

    _ = (email_id, to, subject, body)
    return None
