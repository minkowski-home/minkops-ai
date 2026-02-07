"""State schema for the Kall ticket-resolution agent."""

from __future__ import annotations

import typing

from agents.shared.schemas import Ticket


class KallState(typing.TypedDict):
    """Runtime state for one Kall execution."""

    tenant_id: str
    ticket_id: str
    sender_email: str | None
    ticket: Ticket | None
    resolution_notes: str | None
    outbound_message: str | None
    action: typing.Literal["resolved", "respond", "no_ticket"] | None
