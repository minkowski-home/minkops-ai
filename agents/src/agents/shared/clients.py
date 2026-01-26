"""
This modules contains wrappers for external clients used by the agents, for example Shopify, Stripe, Notion, etc.
"""

def get_chat_model(*, model: str = "gemma3:4b", temperature: float = 0.3):
    """Create a chat model instance.

    Args:
        model: Model identifier to pass through to the provider client.
        temperature: Sampling temperature.

    Returns:
        A LangChain chat model instance.
    """

    import langchain_ollama

    return langchain_ollama.ChatOllama(model=model, temperature=temperature)