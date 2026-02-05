"""Agent registry.

The registry is the single place in the runtime that maps `agent_id` strings to
agent graph entrypoints and the tool contract they require.

This keeps the runtime symmetric as the number of agents grows: adding an agent
is a new `agents.general.<name>` package plus one registry entry here.
"""

from __future__ import annotations

import dataclasses
import typing


TTools = typing.TypeVar("TTools")


@dataclasses.dataclass(frozen=True)
class AgentSpec(typing.Generic[TTools]):
    """Metadata needed to execute an agent graph."""

    agent_id: str
    runner_import: str


def get_agent(agent_id: str) -> AgentSpec:
    """Return an AgentSpec for a known agent id."""

    # Keep this explicit for now; evolve to dynamic discovery once we have more agents.
    if agent_id == "imel":
        return AgentSpec(agent_id="imel", runner_import="agents.general.imel.graph:run_imel")
    raise KeyError(f"Unknown agent_id: {agent_id!r}")
