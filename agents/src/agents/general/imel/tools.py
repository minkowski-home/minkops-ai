"""Imel tool contracts (agent-facing).

This module defines *interfaces* ("ports") that the Imel graph can call to read
from data stores and request side effects, without binding the agent package to
runtime infrastructure (Postgres drivers, provider SDKs, retry loops).

In production, the orchestrator/service layer provides concrete implementations
of these interfaces and injects them into `run_imel(...)` / node functions.
"""

from __future__ import annotations

import typing

from agents.shared.schemas import KBChunk, TenantProfile, Ticket, TicketType

class ImelTools(typing.Protocol):
    """Capabilities required by the current Imel graph.

    Keeping this as a Protocol makes the graph testable: unit tests can inject
    a lightweight fake implementation without any external dependencies.
    """

    def load_tenant_profile(self, *, tenant_id: str | None) -> TenantProfile | None:
        """Load tenant brand/profile details, usually from a KB-backed store."""

    def lookup_company_kb(
        self, *, tenant_id: str | None, query: str, top_k: int = 5
    ) -> list[KBChunk]:
        """Retrieve relevant tenant knowledge chunks for answering inquiries."""

    def create_ticket(
        self,
        *,
        ticket_type: TicketType,
        email_id: str,
        sender_email: str,
        summary: str,
        raw_email: str,
        tenant_id: str,
    ) -> Ticket:
        """Persist a ticket and return the agent-facing ticket shape."""

    def create_agent_handoff(
        self,
        *,
        tenant_id: str,
        run_id: str | None,
        from_agent_id: str,
        to_agent_id: str,
        kind: str = "handoff",
        message: str | None = None,
        payload: dict[str, typing.Any] | None = None,
    ) -> None:
        """Queue an internal handoff/message for another agent."""

    def process_order_update(
        self,
        *,
        tenant_id: str,
        email_id: str,
        summary: str,
        details: dict[str, typing.Any],
    ) -> None:
        """Emit an order-update request (typically via a transactional outbox)."""
