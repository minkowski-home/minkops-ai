from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, START, END  # type: ignore
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
    customer_history: dict | None  # Raw customer data from CRM

    # Generated content
    draft_response: str | None
    messages: list[str] | None
    next_action: Literal['callback_agent', 'account_manager_agent', 'company_kb', 'archive'] | None


# Initialize Gemma 3 via Ollama
gemma = ChatOllama(model="gemma3:4b", 
                    temperature=0.5,
)

# Define the Read Email node
def read_email_node(state: ImelState) -> ImelState:
    '''Node to read an email from the email service(s) and return the update to state with the email content in a HumanMessage()'''
   
    # Define the connection with the email service here
    pass

# Define the Classify Intent node
def classify_intent(state: ImelState) -> ImelState:
    '''Node to classify the intent of the email using Gemma 3, structured as EmailClassification'''
    llm = gemma.with_structured_output(EmailClassification)
    
    classification_prompt = f'''
    Analyze the following email and classify its intent, urgency, topic, and provide a brief summary. Also determine if human intervention is required.
    Email Content: {state["email_content"]}
    From: {state["sender_email"]}
    '''

    classification: EmailClassification = llm.invoke([HumanMessage(content=prompt)])
    
    # Determine the next node based on classification
    routing_prompt = f'''
    Based on the following classification, determine the next action:
    Classification: {classification}
    
    '''