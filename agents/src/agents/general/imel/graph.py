"""Orchestration helpers for the Imel agent.

This module provides a simple "run" function you can call from your service.
Later, if you adopt LangGraph, you can keep the same node functions and just
wire them into a graph.
"""

from __future__ import annotations

from typing import Any

from agents.general.imel.nodes import classify_intent_node, init_imel_state, route_by_intent_node


def run_imel(
    *,
    email_id: str,
    sender_email: str,
    email_content: str,
    tenant_id: str | None = None,
    tenant_brand: dict[str, Any] | None = None,
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

    state = init_imel_state(
        email_id=email_id,
        sender_email=sender_email,
        email_content=email_content,
        tenant_id=tenant_id,
        tenant_brand=tenant_brand,
    )

    state = classify_intent_node(state, llm=llm)
    state = route_by_intent_node(state, llm=llm)
    return state


def build_imel_langgraph():
    """Optional: build a LangGraph graph for Imel.

    You do NOT need this to ship a first version. Keep it for later when you
    want streaming, retries, conditional edges, and observability.
    """

    from langgraph.graph import END, StateGraph

    from agents.general.imel.state import ImelState

    graph = StateGraph(ImelState)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("route_by_intent", route_by_intent_node)
    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "route_by_intent")
    graph.add_edge("route_by_intent", END)
    return graph.compile()

