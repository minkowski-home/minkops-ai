import datetime
import json
import typing
import uuid
from agents.general.imel import state as imel_state


def utc_now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


def create_ticket_in_db(
    *, ticket_type: str, email_id: str, sender_email: str, summary: str, raw_email: str
) -> imel_state.Ticket:
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


def classify_email_heuristic(*, email_content: str, sender_email: str) -> imel_state.EmailClassification:
    """A tiny, dependency-free classifier for demos.

    This keeps your agent runnable before you have:
    - an LLM configured
    - LangChain/LangGraph installed everywhere
    - a robust intent classifier
    """

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


def _safe_json_extract(text: str) -> dict[str, typing.Any]:
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


def coerce_email_classification(payload: dict[str, typing.Any]) -> imel_state.EmailClassification:
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

    import langchain_ollama

    return langchain_ollama.ChatOllama(model=model, temperature=temperature)


def classify_email_via_llm(*, system_prompt: str, email_prompt: str, llm=None) -> imel_state.EmailClassification:
    """Call an LLM to classify an email and return structured JSON."""

    import langchain_core.messages as lc_messages

    llm = llm or get_chat_model()
    result = llm.invoke(
        [lc_messages.SystemMessage(content=system_prompt), lc_messages.HumanMessage(content=email_prompt)]
    )
    payload = _safe_json_extract(getattr(result, "content", str(result)))
    return coerce_email_classification(payload)


def classify_email(
    *, system_prompt: str, email_prompt: str, email_content: str, sender_email: str, llm=None
) -> imel_state.EmailClassification:
    """Classify using an LLM if provided; otherwise use heuristics.

    This design keeps the agent runnable for demos without any external services.
    """

    if llm is None:
        return classify_email_heuristic(email_content=email_content, sender_email=sender_email)
    return classify_email_via_llm(system_prompt=system_prompt, email_prompt=email_prompt, llm=llm)


def draft_reply_via_llm(*, system_prompt: str, draft_prompt: str, llm=None) -> str:
    """Call an LLM to draft a response email."""

    import langchain_core.messages as lc_messages

    llm = llm or get_chat_model()
    result = llm.invoke(
        [lc_messages.SystemMessage(content=system_prompt), lc_messages.HumanMessage(content=draft_prompt)]
    )
    return (getattr(result, "content", str(result)) or "").strip()


def draft_reply(
    *, system_prompt: str, draft_prompt: str, classification: imel_state.EmailClassification | None, llm=None
) -> str:
    """Draft using an LLM if provided; otherwise use a simple template."""

    if llm is not None:
        return draft_reply_via_llm(system_prompt=system_prompt, draft_prompt=draft_prompt, llm=llm)

    # Demo fallback: a short, safe reply that doesn't invent details.
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


def send_email(*, email_id: str, to: str, subject: str, body: str) -> None:
    """Send an email reply.

    TODO(INTEGRATION): Connect to your email provider (Gmail, SES, SendGrid, etc).
    For now this is a no-op; orchestration can still proceed with draft replies.
    """

    _ = (email_id, to, subject, body)
    return None

# TODO
# - `tiktoken` for token counting and prompt size management
# - real DB integration for tickets
# - real email sending integration
# - knowledge base integration for `lookup_company_kb`
# - more robust JSON extraction and validation using Pydantic
