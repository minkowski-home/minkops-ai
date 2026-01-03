from typing import Literal, TypedDict, Any

# Define classification structure
class EmailClassification(TypedDict):
    '''Define the structure for email classification. This will be used with `llm.with_structured_output` to get structured output from the LLM.'''
    intent: Literal['inquiry', 'complaint', 'feedback', 'order_or_account_details', 'update_order', 'cancel_order', 'other', 'spam']
    urgency: Literal['low', 'medium', 'human_intervention_required']
    topic: str
    summary: str
    is_human_intervention_required: bool

# Define the overall state structure for the Email Agent
class ImelState(TypedDict):
    # Raw email data
    email_content: str
    sender_email: str
    email_id: str

    # Classification result
    classification: EmailClassification | None

    # Raw search/API results
    search_results: list[str] | None  # List of raw document chunks
    customer_history: dict[str, Any] | None  # Raw customer data from CRM

    # Generated content
    draft_response: str | None
    messages: list[str] | None