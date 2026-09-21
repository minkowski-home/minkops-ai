"""Orchestration helpers for the Imel agent.

This module exposes both:
- `build_imel_langgraph(...)`: compiled LangGraph object wiring nodes/edges.
- `run_imel(...)`: thin runtime entrypoint that invokes the compiled graph.

Current issues to check later:
 - run_id or email_id is used as thread_id in config
"""

from __future__ import annotations

import functools
import typing

from langgraph.graph import START, StateGraph

from agents.general.imel import nodes as imel_nodes
from agents.general.imel import state as imel_state
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
    run_id: str | None = None,
    llm=None,
):
    """Run Imel by invoking the compiled LangGraph workflow and return the final Imel state dict for this run."""

    # The orchestrator typically loads tenant context and injects it; we keep
    # this convenience fallback so demo runners can omit `tenant_profile`.
    if tenant_profile is None and tenant_id:
        tenant_profile = tools.load_tenant_profile(tenant_id=tenant_id)

    initial_state = imel_nodes.init_imel_state(
        email_id=email_id,
        sender_email=sender_email,
        email_content=email_content,
        tenant_id=tenant_id,
        tenant_profile=tenant_profile,
    )

    graph = build_imel_langgraph(tools=tools, llm=llm)
    # Use run_id as thread_id so runtime and LangGraph traces share the same correlation key.
    config = {"configurable": {"thread_id": run_id or email_id}}
    final_state = graph.invoke(initial_state, config=config)
    return typing.cast(imel_state.ImelState, final_state)


def build_imel_langgraph(*, tools: imel_tools.ImelTools, llm=None):
    """Build and compile the Imel LangGraph workflow.

    Library API note:
    LangGraph nodes accept `state` and may return either state updates or
    `Command(goto=...)`. We bind runtime dependencies (`tools`, `llm`) via
    `functools.partial` so node signatures stay LangGraph-compatible.
    """

    graph = StateGraph(imel_state.ImelState)

    # Register nodes with runtime dependencies bound at graph-build time.
    graph.add_node("classify_intent", functools.partial(imel_nodes.classify_intent_node, llm=llm))
    graph.add_node("route_by_intent", functools.partial(imel_nodes.route_by_intent_node, llm=llm))
    graph.add_node(
        "company_kb_lookup",
        functools.partial(imel_nodes.company_kb_lookup_node, tools=tools),
    )
    graph.add_node("draft_inquiry_response", functools.partial(imel_nodes.draft_inquiry_response_node, llm=llm))
    graph.add_node(
        "process_order",
        functools.partial(imel_nodes.process_order_node, tools=tools),
    )
    graph.add_node(
        "create_ticket_and_handoff_to_kall",
        functools.partial(imel_nodes.create_ticket_and_handoff_to_kall_node, tools=tools),
    )
    graph.add_node("archive", imel_nodes.archive_node)

    # Define fixed edges. Dynamic routing is handled by Command(...) returns.
    graph.add_edge(START, "classify_intent")
    graph.add_edge("classify_intent", "route_by_intent")
    return graph.compile()
