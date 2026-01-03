from __future__ import annotations

from typing import Any, Literal, TypedDict

# Define classification structure
class EmailClassification(TypedDict):
    '''Define the structure for email classification. This will be used with `llm.with_structured_output` to get structured output from the LLM.'''
    intent: Literal['inquiry', 'complaint', 'feedback', 'order_or_account_details', 'update_order', 'cancel_order', 'other', 'spam']
    urgency: Literal['low', 'medium', 'human_intervention_required']
    topic: str
    summary: str
    is_human_intervention_required: bool


class Ticket(TypedDict):
    """A minimal "ticket row" representation.

    In production this would be persisted to a database table (e.g. `tickets`).
    For now we keep it in-memory inside the agent state so you can build the
    orchestration flow before the DB exists.
    """

    ticket_id: str
    ticket_type: Literal["cancel_order", "complaint"]
    status: Literal["open", "closed"]
    email_id: str
    sender_email: str
    summary: str
    raw_email: str


class AgentHandoff(TypedDict):
    """A request to another agent.

    Think of this as a "message" the orchestrator will deliver to a different
    agent (e.g. Order Manager or Kall) along with instructions and context.
    """

    target_agent: Literal["order_manager", "kall"]
    instructions_prompt: str
    context: dict[str, Any]


# Define the overall state structure for the Email Agent
class ImelState(TypedDict):
    # Raw email data
    email_content: str
    sender_email: str
    email_id: str

    # Multi-tenant fields (placeholders until you add a DB)
    tenant_id: str | None
    tenant_brand: dict[str, Any] | None  # TODO(DB): load brand config per tenant/agent

    # Classification result
    classification: EmailClassification | None

    # Raw search/API results
    kb_snippets: list[str] | None  # List of raw knowledge-base snippets/chunks

    # Tickets / handoffs (used for cancel/complaint + order/account flows)
    ticket: Ticket | None
    handoff: AgentHandoff | None

    # Generated content
    draft_response: str | None
    action: Literal["respond", "handoff", "archive"] | None
    messages: list[str] | None
