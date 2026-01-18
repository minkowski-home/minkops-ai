"""Orchestration helpers for the Imel agent.

This module provides a simple "run" function you can call from your service.
Later, if you adopt LangGraph, you can keep the same node functions and just
wire them into a graph.
"""

import typing

from agents.general.imel import nodes as imel_nodes


def run_imel(
    *,
    email_id: str,
    sender_email: str,
    email_content: str,
    tenant_id: str | None = None,
    tenant_brand: dict[str, typing.Any] | None = None,
    llm=None,
):
    """Run Imel on a single email and return the final state.

    This is deliberately written as straight-line Python (no LangGraph required):
    1) Create an initial state
    2) Classify the email intent
    3) Route based on intent to either:
       - respond (draft_response)
       - handoff (handoff payload)
       - archive

    The caller (services/ai-suite) is responsible for:
    - fetching emails from the provider
    - sending the drafted response
    - delivering handoffs to other agents
    - persisting tickets and logs in a real database
    """

    state = imel_nodes.init_imel_state(
        email_id=email_id,
        sender_email=sender_email,
        email_content=email_content,
        tenant_id=tenant_id,
        tenant_brand=tenant_brand,
    )

    state = imel_nodes.classify_intent_node(state, llm=llm)
    state = imel_nodes.route_by_intent_node(state, llm=llm)
    return state


def build_imel_langgraph():
    """Optional: build a LangGraph graph for Imel.

    We do NOT need this to ship a first version. Keeping it for later when we will
    want streaming, retries, conditional edges, and observability.
    """

    import langgraph.graph as langgraph_graph
    from agents.general.imel import state as imel_state

    graph = langgraph_graph.StateGraph(imel_state.ImelState)
    graph.add_node("classify_intent", imel_nodes.classify_intent_node)
    graph.add_node("route_by_intent", imel_nodes.route_by_intent_node)
    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "route_by_intent")
    graph.add_edge("route_by_intent", langgraph_graph.END)
    return graph.compile()
