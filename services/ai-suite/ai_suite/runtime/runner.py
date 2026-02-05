"""Agent execution runner (single-run, CLI-friendly).

This module intentionally provides a *minimal* execution surface:
`run_agent_once(...)` runs exactly one agent on one payload.

In production, this evolves into a worker loop that consumes triggers, persists
checkpoints, and dispatches outbox events.
"""

from __future__ import annotations

import importlib
import json
import logging
import typing
import uuid

from ai_suite.capabilities.email import FakeEmailSender
from ai_suite.capabilities.postgres import PostgresCapabilities
from ai_suite.runtime.registry import AgentSpec

logger = logging.getLogger(__name__)


def _import_attr(path: str):
    """Import an attribute from a `module:attr` string."""

    module_name, attr = path.split(":", 1)
    mod = importlib.import_module(module_name)
    return getattr(mod, attr)


def run_agent_once(
    *,
    agent: AgentSpec,
    tenant_id: str,
    email_id: str,
    sender_email: str,
    email_content: str,
    database_url: str | None,
    use_llm: bool = False,
) -> dict[str, typing.Any]:
    """Run one agent on one email payload and execute service-owned side effects.

    This runner is symmetric across agents: it builds a capability bundle once,
    injects it into the agent entrypoint, and then performs any final "external
    action" (e.g., sending email) based on the returned state.
    """

    if not database_url:
        raise RuntimeError("DATABASE_URL/AGENTS_DB_URL is required to run the orchestrator demo.")

    capabilities = PostgresCapabilities(database_url=database_url)
    email_sender = FakeEmailSender()

    # Create a run row for auditability. This is the core unit of work the runtime owns.
    run_id = str(uuid.uuid4())
    capabilities.runs.create_run(
        run_id=run_id,
        tenant_id=tenant_id,
        agent_id=agent.agent_id,
        input_payload={
            "email_id": email_id,
            "sender_email": sender_email,
        },
    )

    llm = None
    if use_llm:
        # Provider wiring belongs to the service. The agent accepts a model dependency when present.
        from agents.shared import clients as shared_clients

        llm = shared_clients.get_chat_model()

    run_fn = _import_attr(agent.runner_import)

    logger.info("Running agent=%s tenant=%s run_id=%s email_id=%s", agent.agent_id, tenant_id, run_id, email_id)
    try:
        final_state = run_fn(
            email_id=email_id,
            sender_email=sender_email,
            email_content=email_content,
            tenant_id=tenant_id,
            tools=capabilities.imel_tools(),
            llm=llm,
        )

        # Persist the final state as a single checkpoint. In a full runtime we'd checkpoint per node.
        capabilities.state.save_checkpoint(
            run_id=run_id,
            checkpoint_id=1,
            node_name="__end__",
            state_data=json.loads(json.dumps(final_state, default=str)),
        )
        capabilities.runs.mark_completed(run_id=run_id)
    except Exception:
        capabilities.runs.mark_failed(run_id=run_id)
        raise

    # External action demo: "send email" if the agent produced a response.
    if final_state.get("action") == "respond" and final_state.get("draft_response"):
        email_sender.send_email(
            email_id=email_id,
            to=sender_email,
            subject="Re: Your inquiry",
            body=str(final_state["draft_response"]),
        )

    logger.info("Completed run_id=%s action=%s", run_id, final_state.get("action"))
    return typing.cast(dict[str, typing.Any], final_state)
