"""Orchestration helpers for the Kall agent."""

from __future__ import annotations

import functools
import typing

from langgraph.graph import END, START, StateGraph

from agents.general.kall import nodes as kall_nodes
from agents.general.kall import state as kall_state
from agents.general.kall import tools as kall_tools


def run_kall(
    *,
    ticket_id: str,
    tenant_id: str,
    sender_email: str | None = None,
    tools: kall_tools.KallTools,
    run_id: str | None = None,
    llm=None,
):
    """Run Kall by invoking the compiled LangGraph workflow.

    Args:
        ticket_id: Ticket identifier assigned by the support workflow.
        tenant_id: Tenant/workspace identifier.
        sender_email: Optional customer email for outbound status update.
        tools: Runtime-injected Kall capability implementation.
        run_id: Optional runtime run identifier used as LangGraph thread id.
        llm: Reserved for future reasoning/summarization logic nodes.

    Returns:
        Final Kall state for the run.
    """

    _ = llm
    initial_state = kall_nodes.init_kall_state(tenant_id=tenant_id, ticket_id=ticket_id, sender_email=sender_email)
    graph = build_kall_langgraph(tools=tools)
    config = {"configurable": {"thread_id": run_id or ticket_id}}
    final_state = graph.invoke(initial_state, config=config)
    return typing.cast(kall_state.KallState, final_state)


def build_kall_langgraph(*, tools: kall_tools.KallTools):
    """Build and compile the Kall LangGraph workflow."""

    graph = StateGraph(kall_state.KallState)

    # Kall nodes are simple state transforms in the current version.
    graph.add_node("load_ticket", functools.partial(kall_nodes.load_ticket_node, tools=tools))
    graph.add_node("resolve_ticket", functools.partial(kall_nodes.resolve_ticket_node, tools=tools))

    graph.add_edge(START, "load_ticket")
    graph.add_edge("load_ticket", "resolve_ticket")
    graph.add_edge("resolve_ticket", END)
    return graph.compile()
