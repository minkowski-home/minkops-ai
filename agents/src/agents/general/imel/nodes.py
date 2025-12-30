from agents.general.imel.state import ImelState, EmailClassification
from langchain_core.messages import HumanMessage

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
    Analyze the following email and classify its intent, urgency, topic, and provide a brief summary.
    Human intervention is required for high stakes issues which should not be handled by automated systems.
    Email Content: {state["email_content"]}
    From: {state["sender_email"]}
    '''

    classification: EmailClassification = llm.invoke([HumanMessage(content=prompt)])
    
    # Determine the next node based on classification
    # routing_prompt = f'''
    # Based on the following classification, determine the next action:
    # Classification: {classification}
    # For order or account related issues (like order details, account updates, updates to orders placed, etc.), route to 'account_manager_agent'.
    # For feedback, general inquiries or other queries that need company knowledge base to answer, route to 'company_kb'.
    # For order cancellations and complainsts, route to 'callback_agent'.
    # For spams, noreply addresses, or irrelevant emails that do not need to be answered, route to 'archive'.
    # Only output the next_action as one of the following literals: 'callback_agent', 'account_manager_agent', 'company_kb', 'archive'.
    # '''

    if 
    if classification['intent'] == 'order_or_account_details' or classification['intent'] == 'update_order':
        next_action = 'account_manager_agent'