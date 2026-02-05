"""Agent-facing database tool contracts (no runtime DB code).

This module intentionally defines *interfaces* ("ports") only.

Rationale:
The `agents/` package should remain lightweight and importable in environments
that do not have database drivers installed or a live database available. The
service/orchestrator layer owns concrete implementations that talk to Postgres
and enforce transaction/idempotency semantics.

If you need a Postgres-backed implementation, use the runtime service under
`services/ai-suite/` and inject it into your graph runner.
"""

from __future__ import annotations

import typing

from .schemas import Ticket, TicketType


class AgentsDB(typing.Protocol):
    """Capabilities an agent may request from a database-backed tool set."""

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
        """Emit an outbox-style event for asynchronous handling."""


def _moved_error() -> RuntimeError:
    """Consistent error for deprecated direct DB calls from `agents/`."""

    return RuntimeError(
        "Direct DB access has moved to the service/orchestrator layer. "
        "Inject a concrete tool implementation (e.g., `services/ai-suite`) "
        "into your graph runner instead of calling `agents.shared.db` functions."
    )


# Backwards-compatibility shims: these names used to be concrete functions.
# They now fail loudly to prevent silently re-introducing DB writes into `agents/`.
def get_db_conn():  # pragma: no cover - compatibility shim
    raise _moved_error()


def create_ticket(*args, **kwargs):  # pragma: no cover - compatibility shim
    raise _moved_error()


def create_agent_handoff(*args, **kwargs):  # pragma: no cover - compatibility shim
    raise _moved_error()


def process_order_update(*args, **kwargs):  # pragma: no cover - compatibility shim
    raise _moved_error()
