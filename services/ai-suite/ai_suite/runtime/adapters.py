"""Agent runtime adapters.

Each adapter owns agent-specific payload validation, runner kwargs mapping, and
post-run side effects. The core runner stays generic and agent-agnostic.

An adapter is glue between two interfaces that shouldn’t know about each other directly.
In our repo it’s “agent runtime adapter”: it converts a generic trigger payload into the
exact call signature the agent graph expects, and converts the agent’s final state/intent
into runtime-owned actions (send email, enqueue outbox, handoff).
This is very standard as a pattern (Adapter pattern, “ports and adapters”).
"""

from __future__ import annotations

import logging
import typing
import uuid

from ai_suite.capabilities.email import FakeEmailSender
from ai_suite.capabilities.postgres import PostgresCapabilities

logger = logging.getLogger(__name__)


class AgentRuntimeAdapter(typing.Protocol):
    """Contract for plugging heterogeneous agents into a generic runner.
    A Protocol is basically an interface contract for static type checking: it says
    "any adapter must have these three functions".
    Although ImelRuntimeAdapter or KallRuntimeAdapter etc don't strictly need to inherit from it,
    it's a good idea. The main purpose of this Protocol is IDE specific type checking, or use in Annotations, etc.
    However, a Protocol doesn't "enforce" type checking, you must enforce one at CI (or use it as annotation).
    """

    def validate_payload(self, payload: dict[str, typing.Any]) -> dict[str, typing.Any]:
        """Validate and normalize an incoming trigger payload."""

    def build_run_kwargs(
        self,
        *,
        tenant_id: str,
        run_id: str,
        payload: dict[str, typing.Any],
        capabilities: PostgresCapabilities,
        llm: typing.Any,
    ) -> dict[str, typing.Any]:
        """Translate normalized payload into keyword args for the agent runner."""

    def handle_post_run(
        self,
        *,
        tenant_id: str,
        payload: dict[str, typing.Any],
        final_state: dict[str, typing.Any],
        email_sender: FakeEmailSender,
    ) -> None:
        """Execute post-run actions such as sending customer-facing notifications."""


class ImelRuntimeAdapter:
    """Imel-specific mapping between trigger payload and `run_imel(...)`."""

    def validate_payload(self, payload: dict[str, typing.Any]) -> dict[str, typing.Any]:
        sender_email = str(payload.get("sender_email") or "").strip()
        email_content = str(payload.get("email_content") or "").strip()
        if not sender_email:
            raise ValueError("Imel payload requires `sender_email`.")
        if not email_content:
            raise ValueError("Imel payload requires `email_content`.")
        email_id = str(payload.get("email_id") or str(uuid.uuid4()))
        return {
            "email_id": email_id,
            "sender_email": sender_email,
            "email_content": email_content,
        }

    def build_run_kwargs(
        self,
        *,
        tenant_id: str,
        run_id: str,
        payload: dict[str, typing.Any],
        capabilities: PostgresCapabilities,
        llm: typing.Any,
    ) -> dict[str, typing.Any]:
        return {
            "email_id": payload["email_id"],
            "sender_email": payload["sender_email"],
            "email_content": payload["email_content"],
            "tenant_id": tenant_id,
            "tools": capabilities.imel_tools(),
            "run_id": run_id,
            "llm": llm,
        }

    def handle_post_run(
        self,
        *,
        tenant_id: str,
        payload: dict[str, typing.Any],
        final_state: dict[str, typing.Any],
        email_sender: FakeEmailSender,
    ) -> None:
        # Runtime owns external effects; agent state only expresses intent.
        # In production, these should be written to outbox instead of direct implementation here.
        if final_state.get("action") == "respond" and final_state.get("draft_response"):
            email_sender.send_email(
                email_id=str(payload["email_id"]),
                to=str(payload["sender_email"]),
                subject="Re: Your inquiry",
                body=str(final_state["draft_response"]),
            )


class KallRuntimeAdapter:
    """Kall-specific mapping between trigger payload and `run_kall(...)`."""

    def validate_payload(self, payload: dict[str, typing.Any]) -> dict[str, typing.Any]:
        ticket_id = str(payload.get("ticket_id") or "").strip()
        if not ticket_id:
            raise ValueError("Kall payload requires `ticket_id`.")

        sender_email_raw = payload.get("sender_email")
        sender_email = str(sender_email_raw).strip() if sender_email_raw else None
        return {"ticket_id": ticket_id, "sender_email": sender_email}

    def build_run_kwargs(
        self,
        *,
        tenant_id: str,
        run_id: str,
        payload: dict[str, typing.Any],
        capabilities: PostgresCapabilities,
        llm: typing.Any,
    ) -> dict[str, typing.Any]:
        return {
            "ticket_id": payload["ticket_id"],
            "tenant_id": tenant_id,
            "sender_email": payload.get("sender_email"),
            "tools": capabilities.kall_tools(),
            "run_id": run_id,
            "llm": llm,
        }

    def handle_post_run(
        self,
        *,
        tenant_id: str,
        payload: dict[str, typing.Any],
        final_state: dict[str, typing.Any],
        email_sender: FakeEmailSender,
    ) -> None:
        sender_email = payload.get("sender_email")
        outbound_message = final_state.get("outbound_message")
        if sender_email and final_state.get("action") == "respond" and outbound_message:
            email_sender.send_email(
                email_id=str(final_state.get("email_id") or payload["ticket_id"]),
                to=str(sender_email),
                subject="Update on your support request",
                body=str(outbound_message),
            )
