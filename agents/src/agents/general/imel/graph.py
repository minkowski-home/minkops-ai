from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
import os
import dotenv

dotenv.load_dotenv()

# Define classification structure
class EmailClassification(TypedDict):
    '''Define the structure for email classification. This will be used with `llm.with_structured_output` to get structured output from the LLM.'''
    intent: Literal['inquiry', 'complaint', 'feedback', 'order_or_account_details', 'update_order', 'cancel_order', 'other']
    urgency: Literal['low', 'medium', 'high']
    topic: str
    summary: str
    is_human_required: bool

# Define the overall state structure for the Email Agent
class EmailAgentState(TypedDict):
    # Raw email data
    email_content: str
    sender_email: str
    email_id: str

    # Classification result
    classification: EmailClassification | None

    # Raw search/API results
    search_results: list[str] | None  # List of raw document chunks
    customer_history: dict | None  # Raw customer data from CRM

    # Generated content
    draft_response: str | None
    messages: list[str] | None


# Initialize Gemma 3 via Ollama
gemma = ChatOllama(model="gemma3:4b", 
                    temperature=0.5,
)


# Define the Read Email node
def read_email_node(state: ImelState) -> ImelState:
    '''Node to read an email from the email service(s) and return the update to state with the email content in a HumanMessage()'''
   
    # Define the connection with the email service here
    pass