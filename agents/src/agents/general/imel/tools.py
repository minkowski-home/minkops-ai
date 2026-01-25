"""Imel agent tools and integrations.

This module keeps external dependencies (LLMs, embeddings, DB access) behind a
small set of functions so the rest of the agent can remain plain Python. Most
functions have safe, dependency-free fallbacks to keep local development simple.
"""

import datetime
import json
import logging
import os
import typing
import uuid
from typing import Sequence

from agents.general.imel import state as imel_state

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 1536


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


def create_ticket_in_db(
    *, ticket_type: str, email_id: str, sender_email: str, summary: str, raw_email: str
) -> imel_state.Ticket:
    """Create a ticket for human follow-up.

    TODO(DB): Insert into a real `tickets` table and return the inserted row.
    Suggested columns: ticket_id (uuid), type, status, email_id, sender_email,
    summary, raw_email, created_at, updated_at.

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


def _get_db_conn():
    """Return a Postgres connection if AGENTS_DB_URL/DATABASE_URL is set.

    Returns:
        A DB connection object, or `None` if not configured or unavailable.
    """

    db_url = os.getenv("AGENTS_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        import psycopg2  # type: ignore

        return psycopg2.connect(db_url)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("DB connection unavailable for KB lookup: %s", exc)
        return None


def _format_pgvector(values: Sequence[float]) -> str:
    """Format a Python sequence into a pgvector literal.

    Args:
        values: Vector values to format.

    Returns:
        A pgvector literal string (e.g., "[0.123000,0.456000,...]").
    """

    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


def _get_default_embedder():
    """Create a default embeddings client if configured.

    Returns:
        An embeddings client, or `None` if the optional dependency or API key is missing.
    """

    try:
        from langchain_openai import OpenAIEmbeddings
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.debug("OpenAIEmbeddings unavailable: %s", exc)
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set; skipping KB vector lookup")
        return None

    return OpenAIEmbeddings(api_key=api_key)


def lookup_company_kb(
    *,
    tenant_id: str | None,
    query: str,
    top_k: int = 5,
    embedder=None,
    conn=None,
) -> list[imel_state.KBChunk]:
    """Return KB chunks via pgvector similarity search, per tenant.

    Args:
        tenant_id: Tenant identifier used to scope retrieval.
        query: Natural language query built from the email + classification.
        top_k: Max number of chunks to return.
        embedder: Optional embeddings client with an `embed_query(str)` method.
        conn: Optional existing DB connection.

    Returns:
        A list of KB chunks with provenance; empty if not configured or unavailable.
    """

    if not tenant_id:
        logger.info("Skipping KB lookup because tenant_id is missing")
        return []

    embedder = embedder or _get_default_embedder()
    if embedder is None:
        logger.info("No embedder configured; returning empty KB snippets for tenant %s", tenant_id)
        return []

    try:
        query_vector = embedder.embed_query(query)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to embed KB query for tenant %s: %s", tenant_id, exc)
        return []

    if len(query_vector) != EMBEDDING_DIMENSION:
        logger.debug(
            "KB embed dimension (%s) != expected (%s); proceeding anyway",
            len(query_vector),
            EMBEDDING_DIMENSION,
        )

    vector_literal = _format_pgvector(query_vector)

    close_conn = False
    if conn is None:
        conn = _get_db_conn()
        close_conn = conn is not None

    if conn is None:
        logger.info("No DB connection available; returning empty KB snippets for tenant %s", tenant_id)
        return []

    rows: list[tuple[str, dict[str, typing.Any], str | None, str | None]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata, source_uri, source_type
                FROM tenant_kb_chunks
                WHERE tenant_id = %s
                ORDER BY embedding <-> (%s)::vector
                LIMIT %s
                """,
                (tenant_id, vector_literal, top_k),
            )
            rows = cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("KB lookup failed for tenant %s: %s", tenant_id, exc)
        return []
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass

    snippets: list[imel_state.KBChunk] = []
    for content, metadata, source_uri, source_type in rows:
        metadata = metadata or {}
        snippet: imel_state.KBChunk = {
            "content": content,
            "metadata": metadata,
            "source_uri": source_uri or metadata.get("source_uri"),
            "source_type": source_type or metadata.get("source_type"),
        }
        snippets.append(snippet)
    return snippets


def load_tenant_profile(*, tenant_id: str | None, conn=None) -> imel_state.TenantProfile | None:
    """Load tenant branding/profile details from KB (brand_kit chunks).

    Args:
        tenant_id: Tenant identifier used to scope retrieval.
        conn: Optional existing DB connection.

    Returns:
        The latest tenant profile data found, or `None` if unavailable.
    """

    if not tenant_id:
        return None

    close_conn = False
    if conn is None:
        conn = _get_db_conn()
        close_conn = conn is not None

    if conn is None:
        return None

    row: tuple[str, dict[str, typing.Any], str | None] | None = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata, source_uri
                FROM tenant_kb_chunks
                WHERE tenant_id = %s
                  AND (source_type = 'brand_kit' OR metadata->>'kind' = 'brand_kit')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("No tenant profile found for %s: %s", tenant_id, exc)
        return None
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass

    if not row:
        return None

    content, metadata, source_uri = row
    metadata = metadata or {}
    profile: imel_state.TenantProfile = {
        "brand_kit_text": content or "",
        "brand_kit": metadata.get("brand_kit", {}) if isinstance(metadata.get("brand_kit"), dict) else {},
        "source_uri": source_uri or metadata.get("source_uri", ""),
    }

    for key in ("agent_display_name", "tone", "keywords", "email_signature"):
        value = metadata.get(key)
        if value:
            profile[key] = value

    return profile


def classify_email_heuristic(*, email_content: str, sender_email: str) -> imel_state.EmailClassification:
    """A tiny, dependency-free classifier for demos.

    This keeps your agent runnable before you have:
    - an LLM configured
    - LangChain/LangGraph installed everywhere
    - a robust intent classifier

    Args:
        email_content: Raw email body.
        sender_email: Sender address of the inbound email.

    Returns:
        A best-effort `EmailClassification` based on simple string matching.
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
    """Best-effort JSON extraction from an LLM response.

    Args:
        text: LLM response text, possibly containing JSON in markdown fences.

    Returns:
        Parsed JSON object.

    Raises:
        json.JSONDecodeError: If no valid JSON object can be extracted.
    """

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

    Args:
        payload: Untrusted JSON payload parsed from an LLM response.

    Returns:
        A normalized `EmailClassification` with safe fallbacks for unknown values.
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

    Args:
        model: Model identifier to pass through to the provider client.
        temperature: Sampling temperature.

    Returns:
        A LangChain chat model instance.
    """

    import langchain_ollama

    return langchain_ollama.ChatOllama(model=model, temperature=temperature)


def classify_email_via_llm(*, system_prompt: str, email_prompt: str, llm=None) -> imel_state.EmailClassification:
    """Call an LLM to classify an email and return structured JSON.

    Args:
        system_prompt: System prompt (policy/persona).
        email_prompt: User prompt containing the email content.
        llm: Optional chat model instance.

    Returns:
        A normalized `EmailClassification`.
    """

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

    Args:
        system_prompt: System prompt (policy/persona).
        email_prompt: User prompt containing the email content.
        email_content: Raw email body (used for heuristic fallback).
        sender_email: Sender address (used for heuristic fallback).
        llm: Optional chat model instance to use for classification.

    Returns:
        A normalized `EmailClassification`.
    """

    if llm is None:
        return classify_email_heuristic(email_content=email_content, sender_email=sender_email)
    return classify_email_via_llm(system_prompt=system_prompt, email_prompt=email_prompt, llm=llm)


def draft_reply_via_llm(*, system_prompt: str, draft_prompt: str, llm=None) -> str:
    """Call an LLM to draft a response email.

    Args:
        system_prompt: System prompt (policy/persona).
        draft_prompt: User prompt containing the email + any KB snippets.
        llm: Optional chat model instance.

    Returns:
        The drafted reply text.
    """

    import langchain_core.messages as lc_messages

    llm = llm or get_chat_model()
    result = llm.invoke(
        [lc_messages.SystemMessage(content=system_prompt), lc_messages.HumanMessage(content=draft_prompt)]
    )
    return (getattr(result, "content", str(result)) or "").strip()


def draft_reply(
    *, system_prompt: str, draft_prompt: str, classification: imel_state.EmailClassification | None, llm=None
) -> str:
    """Draft using an LLM if provided; otherwise use a simple template.

    Args:
        system_prompt: System prompt (policy/persona).
        draft_prompt: User prompt containing the email + any KB snippets.
        classification: Optional classification results used for safe templating.
        llm: Optional chat model instance to use for drafting.

    Returns:
        The drafted reply text.
    """

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

    Args:
        email_id: Provider or internal identifier for the inbound email.
        to: Recipient address.
        subject: Email subject line.
        body: Email body content.
    """

    _ = (email_id, to, subject, body)
    return None

# TODO
# - `tiktoken` for token counting and prompt size management
# - real DB integration for tickets
# - real email sending integration
# - knowledge base integration for `lookup_company_kb`
# - more robust JSON extraction and validation using Pydantic
