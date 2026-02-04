"""Shared schema/type definitions for agents.

This module intentionally contains *only* lightweight typing constructs (e.g.,
`typing.TypedDict`, `typing.Literal`) and zero runtime dependencies. The goal is
to let "state" modules (which should remain importable in any environment) share
consistent shapes with DB/KB helper modules *without* importing heavyweight
libraries (e.g., database drivers) or creating accidental layering/coupling.
"""

from __future__ import annotations

import typing


# ---- Tickets -----------------------------------------------------------------

# Keep ticket fields constrained to known categories/statuses for better static
# checking. If/when new ticket types are added, extend these Literals in one
# place so call sites and storage helpers stay aligned.
TicketType = typing.Literal["cancel_order", "complaint"]
TicketStatus = typing.Literal["open", "closed"]


class Ticket(typing.TypedDict):
    """A minimal "ticket row" representation shared across agents.

    This is the canonical in-code shape for a ticket returned from persistence
    helpers and stored in agent state. The actual DB table may have more columns
    (timestamps, tenant_id, etc.); those are intentionally not modeled here so
    the agent-facing contract stays stable.
    """

    ticket_id: str
    ticket_type: TicketType
    status: TicketStatus
    email_id: str
    sender_email: str
    summary: str
    raw_email: str


# ---- Knowledge base ----------------------------------------------------------

class KBChunk(typing.TypedDict, total=False):
    """A single retrieved KB chunk with provenance.

    `content` is required; all other fields are optional because different KB
    backends may provide different metadata/provenance signals.
    """

    content: typing.Required[str]
    source_uri: str | None
    source_type: str | None
    metadata: dict[str, typing.Any]
    score: float | None


class TenantProfile(typing.TypedDict):
    """Tenant-specific branding/profile details loaded from a KB or database.

    The required fields are chosen to make downstream prompt-building simpler
    (callers can rely on keys existing, even if empty). Optional keys are
    included only when present in the source data.
    """

    brand_kit_text: str
    brand_kit: dict[str, str]
    source_uri: str
    agent_display_name: typing.NotRequired[str]
    tone: typing.NotRequired[str]
    keywords: typing.NotRequired[list[str]]
    email_signature: typing.NotRequired[str]
