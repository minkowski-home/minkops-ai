"""Orchestration helpers for the Imel agent.

This module provides a simple "run" function you can call from your service.
Later, if you adopt LangGraph, you can keep the same node functions and just
wire them into a graph.
"""

import typing

from agents.general.imel import nodes as imel_nodes
from agents.general.imel import tools as imel_tools
from agents.shared.schemas import TenantProfile


def run_imel(
    *,
    email_id: str,
    sender_email: str,
    email_content: str,
    tenant_id: str | None = None,
    tenant_profile: TenantProfile | None = None,
    tools: imel_tools.ImelTools,
    llm=None,
):
    """Run Imel on a single email and return the final state.

    This runner is intentionally lightweight and service-friendly: it executes
    the same node functions used by LangGraph by following `Command(goto=...)`
    transitions in a small loop.

    The caller (services/ai-suite) is responsible for:
    - fetching emails from the provider
    - sending the drafted response
    - delivering handoffs to other agents
    - persisting tickets and logs in a real database

    Args:
        email_id: Provider or internal identifier for the inbound email.
        sender_email: Sender address of the inbound email.
        email_content: Raw email body (plain text or pre-rendered content).
        tenant_id: Optional tenant identifier for multi-tenant deployments.
        tenant_profile: Optional tenant branding/profile details. If omitted and
            `tenant_id` is provided, this will attempt to load via `tools`.
        tools: Service-layer implementation of the tool contracts required by the graph.
        llm: Optional chat model instance to use for LLM-backed steps.

    Returns:
        The final Imel state dict for this run.
    """

    # The orchestrator typically loads tenant context and injects it; we keep
    # this convenience fallback so demo runners can omit `tenant_profile`.
    if tenant_profile is None and tenant_id:
        tenant_profile = tools.load_tenant_profile(tenant_id=tenant_id)

    state = imel_nodes.init_imel_state(
        email_id=email_id,
        sender_email=sender_email,
        email_content=email_content,
        tenant_id=tenant_id,
        tenant_profile=tenant_profile,
    )

    state = imel_nodes.classify_intent_node(state, llm=llm)
    command = imel_nodes.route_by_intent_node(state, llm=llm)

    # Minimal interpreter for LangGraph `Command` objects. This keeps agent nodes
    # consistent whether they're run via LangGraph or directly by a service.
    while True:
        update = getattr(command, "update", None)
        if update:
            state.update(update)

        goto = getattr(command, "goto", None)
        if goto in (None, "__end__"):
            return state

        if goto == "company_kb_lookup":
            command = imel_nodes.company_kb_lookup_node(state, tools=tools)
        elif goto == "draft_inquiry_response":
            command = imel_nodes.draft_inquiry_response_node(state, llm=llm)
        elif goto == "process_order":
            command = imel_nodes.process_order_node(state, tools=tools)
        elif goto == "create_ticket_and_handoff_to_kall":
            command = imel_nodes.create_ticket_and_handoff_to_kall_node(state, tools=tools)
        elif goto == "archive":
            command = imel_nodes.archive_node(state)
        else:
            raise ValueError(f"Unknown graph node transition: {goto!r}")


def build_imel_langgraph(*, tools: imel_tools.ImelTools):
    """Optional: build a LangGraph graph for Imel.

    We do NOT need this to ship a first version. Keeping it for later when we will
    want streaming, retries, conditional edges, and observability.

    Returns:
        A compiled LangGraph graph.

    Raises:
        ImportError: If LangGraph is not installed.
    """

    import functools
    import langgraph.graph as langgraph_graph
    from agents.general.imel import state as imel_state

    graph = langgraph_graph.StateGraph(imel_state.ImelState)
    
    # Register Nodes
    graph.add_node("classify_intent", imel_nodes.classify_intent_node)
    graph.add_node("route_by_intent", imel_nodes.route_by_intent_node)
    graph.add_node(
        "company_kb_lookup",
        functools.partial(imel_nodes.company_kb_lookup_node, tools=tools),
    )
    graph.add_node("draft_inquiry_response", imel_nodes.draft_inquiry_response_node)
    graph.add_node(
        "process_order",
        functools.partial(imel_nodes.process_order_node, tools=tools),
    )
    graph.add_node(
        "create_ticket_and_handoff_to_kall",
        functools.partial(imel_nodes.create_ticket_and_handoff_to_kall_node, tools=tools),
    )
    graph.add_node("archive", imel_nodes.archive_node)

    # Define Edges
    graph.set_entry_point("classify_intent")
    
    # Static edge: always route to router after classification
    graph.add_edge("classify_intent", "route_by_intent")

    # Command-based routing happens in 'route_by_intent', 'company_kb_lookup', and 'process_order'.
    # We implicitly define that they can go to their Command targets.
    # Note: Explicit edge company_kb_lookup -> draft_inquiry_response matches the Command,
    # but strictly speaking Command overrides.
    
    return graph.compile()
