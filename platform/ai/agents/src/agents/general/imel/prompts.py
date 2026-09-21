"""Prompt templates for the Imel agent.

These are plain strings so they can be read/edited without any LangChain/LangGraph
knowledge. The orchestrator (or node functions) will combine these templates with
the system prompt built from `policy.py`.
"""

# The classifier is expected to return JSON so we can parse it deterministically.
# This makes the system easier to test than relying on free-form text outputs.
CLASSIFY_EMAIL_PROMPT = """Classify the email below into a JSON object.

Return ONLY valid JSON with the following keys:
- intent: one of ["inquiry","complaint","feedback","order_or_account_details","update_order","cancel_order","other","spam"]
- urgency: one of ["low","medium","human_intervention_required"]
- topic: short topic string
- summary: 1-2 sentence summary
- is_human_intervention_required: boolean

Email content:
{email_content}

From:
{sender_email}
"""


INQUIRY_DRAFT_REPLY_PROMPT = """Draft a reply email.

Constraints:
- Be concise and professional.
- Do not invent facts; if needed info is missing, ask for it.
- Use the knowledge base snippets if they are relevant; otherwise ignore them.

Email content:
{email_content}

Knowledge base snippets (may be empty):
{kb_snippets}
"""


# This is sent to the Order Manager agent (not Imel) so that only that agent is
# responsible for touching orders/accounts/products data.
ORDER_MANAGER_HANDOFF_INSTRUCTIONS = """You are the Order Manager agent.

You have access to the orders/accounts/products database(s). Imel does NOT.
Your job is to:
- Read the customer's email and Imel's classification.
- Pull any needed customer/order/account/product records from the DB.
- Decide the correct action (update order, provide order details, update account, etc.).
- Produce a status ("ok" or "needs_human") and a proposed email reply draft.

Return your result in a simple dict/object with:
- status: "ok" | "needs_human"
- summary: what you did / found
- reply_draft: the email Imel should send (or empty if needs_human)
"""


# This is sent to Kall for follow-ups that must be handled by a human-like callback agent.
KALL_HANDOFF_INSTRUCTIONS = """You are Kall, the callback/follow-up agent.

You must follow up on ALL complaints and ALL cancel-order requests.
Your job is to:
- Review the ticket + original email.
- Decide next steps (call the customer, request more info, escalate internally).
- Update the ticket status as the work progresses.

Return a short plan and, if appropriate, a short acknowledgement email draft.
"""
