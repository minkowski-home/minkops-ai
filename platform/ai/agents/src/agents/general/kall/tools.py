"""Kall tool contracts (agent-facing).

Kall focuses on resolving human-escalated tickets. The runtime injects a
concrete implementation of these capabilities (DB, inter-agent messaging).
"""

from __future__ import annotations

import typing

from agents.shared.schemas import Ticket, TicketStatus


class KallTools(typing.Protocol):
    """Capabilities required by the current Kall graph."""

    def get_ticket(self, *, ticket_id: str, tenant_id: str) -> Ticket | None:
        """Load a ticket from storage in the agent-facing shape."""

    def update_ticket_status(self, *, ticket_id: str, tenant_id: str, status: TicketStatus) -> None:
        """Persist a status transition for a ticket."""

    def create_agent_handoff(
        self,
        *,
        tenant_id: str,
        run_id: str | None,
        from_agent_id: str,
        to_agent_id: str,
        kind: str = "message",
        message: str | None = None,
        payload: dict[str, typing.Any] | None = None,
    ) -> None:
        """Send a cross-agent message via the intercom queue."""
