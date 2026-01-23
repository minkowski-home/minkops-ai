"""State and schema definitions for the Imel email agent.

These types are intentionally lightweight (built on `typing.TypedDict`) so the
rest of the agent can stay plain Python. The orchestrator owns persistence; the
agent state is treated as an in-memory, request-scoped data structure.
"""

import typing


class EmailClassification(typing.TypedDict):
    """Structured intent classification returned by the classifier."""

    intent: typing.Literal[
        "inquiry",
        "complaint",
        "feedback",
        "order_or_account_details",
        "update_order",
        "cancel_order",
        "other",
        "spam",
    ]
    urgency: typing.Literal["low", "medium", "human_intervention_required"]
    topic: str
    summary: str
    is_human_intervention_required: bool


class Ticket(typing.TypedDict):
    """A minimal "ticket row" representation.

    In production this would be persisted to a database table (e.g. `tickets`).
    For now we keep it in-memory inside the agent state so you can build the
    orchestration flow before the DB exists.
    """

    ticket_id: str
    ticket_type: typing.Literal["cancel_order", "complaint"]
    status: typing.Literal["open", "closed"]
    email_id: str
    sender_email: str
    summary: str
    raw_email: str


class AgentHandoff(typing.TypedDict):
    """A request to another agent.

    Think of this as a "message" the orchestrator will deliver to a different
    agent (e.g. Order Manager or Kall) along with instructions and context.
    """

    target_agent: typing.Literal["order_manager", "kall"]
    instructions_prompt: str
    context: dict[str, typing.Any]


class TenantProfile(typing.TypedDict, total=False):
    """Tenant-specific branding/profile details pulled from the KB."""

    agent_display_name: str
    tone: str
    keywords: list[str]
    email_signature: str
    brand_kit: dict[str, str]
    brand_kit_text: str
    source_uri: str


class KBChunk(typing.TypedDict, total=False):
    """A single retrieved KB chunk with provenance."""

    content: str
    source_uri: str | None
    source_type: str | None
    metadata: dict[str, typing.Any]
    score: float | None


# Define the overall state structure for the Email Agent
class ImelState(typing.TypedDict):
    """End-to-end state for a single Imel run.

    Keys are populated gradually as the run progresses (e.g., `classification`,
    then `kb_snippets`, then either `draft_response` or `handoff`).
    """

    # Raw email data
    email_content: str
    sender_email: str
    email_id: str

    # Multi-tenant fields (loaded from DB/KB)
    tenant_id: str | None
    tenant_profile: TenantProfile | None  # Loaded from vector-backed KB

    # Classification result
    classification: EmailClassification | None

    # Raw search/API results
    kb_snippets: list[KBChunk] | None  # List of KB chunks with provenance

    # Tickets / handoffs (used for cancel/complaint + order/account flows)
    ticket: Ticket | None
    handoff: AgentHandoff | None

    # Generated content
    draft_response: str | None
    action: typing.Literal["respond", "handoff", "archive"] | None
    messages: list[str] | None
