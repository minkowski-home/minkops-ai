"""Imel tool contracts (agent-facing).

This module defines *interfaces* ("ports") that the Imel graph can call to read
from data stores and request side effects, without binding the agent package to
runtime infrastructure (Postgres drivers, provider SDKs, retry loops).

In production, the orchestrator/service layer provides concrete implementations
of these interfaces and injects them into `run_imel(...)` / node functions.

A Protocol (from typing) is basically an “interface” in Python: it describes
the methods/attributes an object must have, without caring what concrete class it is.
It’s used so agent code can say “I need something that can create_ticket(...) and
lookup_company_kb(...)” without importing Postgres code or email provider code.
The orchestrator then injects any object that matches that shape
(a real Postgres-backed implementation in prod, a fake in tests).
This is standard “dependency inversion” / “ports and adapters” design in Python.
"""

from __future__ import annotations

import typing

from agents.shared.schemas import KBChunk, TenantProfile, Ticket, TicketType

import logging

logger = logging.getLogger(__name__)

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


def send_email(*, email_id: str, to: str, subject: str, body: str) -> None:
    """
    Either remove it or convert it into a contract. The actual email functionality happens in services/ai-suite/capabilities.
    """
    pass
