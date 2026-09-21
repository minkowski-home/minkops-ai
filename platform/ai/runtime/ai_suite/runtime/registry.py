"""Agent registry.

The registry is the single place in the runtime that maps `agent_id` strings to
agent graph entrypoints and the tool contract they require.

This keeps the runtime symmetric as the number of agents grows: adding an agent
is a new `agents.general.<name>` package plus one registry entry here.
Think of it as configuration/lookup/metadata, not a level in architecture.
"""

from __future__ import annotations

import dataclasses
import typing


@dataclasses.dataclass(frozen=True)
class AgentSpec:
    """Metadata needed to execute an agent graph."""

    agent_id: str
    runner_import: str
    adapter_import: str


def get_agent(agent_id: str) -> AgentSpec:
    """Return an AgentSpec for a known agent id."""

    # Keep this explicit for now; evolve to dynamic discovery once we have more agents.
    if agent_id == "imel":
        return AgentSpec(
            agent_id="imel",
            runner_import="agents.general.imel.graph:run_imel",
            adapter_import="ai_suite.runtime.adapters:ImelRuntimeAdapter",
        )
    if agent_id == "kall":
        return AgentSpec(
            agent_id="kall",
            runner_import="agents.general.kall.graph:run_kall",
            adapter_import="ai_suite.runtime.adapters:KallRuntimeAdapter",
        )
    raise KeyError(f"Unknown agent_id: {agent_id!r}")
