"""CLI entrypoints for the AI Suite agent runtime orchestrator.

This CLI is intentionally minimal:

- `seed-db` resets the dev database using the canonical SQL file in `db/`.
- `run-imel` runs the Imel agent end-to-end on a single email payload.

As additional agents are introduced, add symmetrical commands like `run-kall`,
or a generic `run-agent --agent-id ...`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import typing

from ai_suite.config import load_settings
from ai_suite.persistence.seed import seed_database
from ai_suite.runtime.registry import get_agent
from ai_suite.runtime.runner import run_agent_once


def _read_stdin() -> str:
    """Read all stdin content (used for piping an email body)."""

    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _parse_input_json(value: str) -> dict[str, typing.Any]:
    """Parse a JSON object string into a dictionary."""

    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:  # pragma: no cover - user input
        raise SystemExit(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Input payload must be a JSON object.")
    return typing.cast(dict[str, typing.Any], data)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser with subcommands."""

    parser = argparse.ArgumentParser(description="AI Suite: agent runtime orchestrator (dev CLI).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser(
        "seed-db",
        help="Drop & recreate all tables in minkops_app using db/schema.sql (DANGEROUS). Run db/bootstrap.sql first if the database does not exist.",
    )
    seed.add_argument(
        "--tenant-id",
        default="tenant_001",
        help="Tenant id to upsert and seed KB content for (default: tenant_001).",
    )
    seed.add_argument(
        "--kb-path",
        default="data/tenant_001/company_kb/kb.md",
        help="Path to a markdown KB/brand-kit file to load into tenant_kb_chunks.",
    )
    seed.add_argument(
        "--sql-path",
        default="db/schema.sql",
        help="Path to the psql schema SQL file (default: db/schema.sql).",
    )

    run_agent = sub.add_parser("run-agent", help="Run any registered agent using a JSON payload.")
    run_agent.add_argument("--agent-id", required=True, help="Registered agent id (e.g., imel, kall).")
    run_agent.add_argument("--tenant-id", default="tenant_001", help="Tenant id for the run.")
    run_agent.add_argument(
        "--input-json",
        default=None,
        help="JSON object payload. If omitted, payload is read from stdin.",
    )
    run_agent.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured LLM for agents that support it.",
    )

    imel = sub.add_parser("run-imel", help="Run the Imel agent (email convenience wrapper).")
    imel.add_argument("--tenant-id", default="tenant_001", help="Tenant id for the run.")
    imel.add_argument("--sender", default="customer@example.com", help="Sender email address.")
    imel.add_argument(
        "--email",
        default=None,
        help="Email content as a string. If omitted, reads from stdin.",
    )
    imel.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured LLM (requires LangChain + Ollama/OpenAI).",
    )

    kall = sub.add_parser("run-kall", help="Run the Kall agent (ticket convenience wrapper).")
    kall.add_argument("--tenant-id", default="tenant_001", help="Tenant id for the run.")
    kall.add_argument("--ticket-id", required=True, help="Ticket id Kall should process.")
    kall.add_argument(
        "--sender",
        default=None,
        help="Optional sender email for customer update notification.",
    )
    kall.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured LLM for agents that support it.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main function. Returns a process exit code."""

    args = build_parser().parse_args(argv)
    settings = load_settings()

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(message)s")

    if args.cmd == "seed-db":
        seed_database(
            sql_path=args.sql_path,
            tenant_id=args.tenant_id,
            kb_markdown_path=args.kb_path,
            database_url=settings.database_url,
            psql_path=settings.psql_path,
        )
        return 0

    if args.cmd == "run-agent": # the only mandatory part to run agents. "run-imel" and "run-kall" are just convenience shortcuts.
        payload_raw = args.input_json if args.input_json is not None else _read_stdin()
        if not payload_raw.strip():
            raise SystemExit("Provide input payload via --input-json or stdin.")

        agent = get_agent(args.agent_id)
        final_state = run_agent_once(
            agent=agent,
            tenant_id=args.tenant_id,
            input_payload=_parse_input_json(payload_raw),
            database_url=settings.database_url,
            use_llm=args.use_llm,
        )

        print("\n=== FINAL STATE ===")
        print(json.dumps(final_state, indent=2, default=str))
        return 0

    if args.cmd == "run-imel":
        email_content = args.email if args.email is not None else _read_stdin()
        if not email_content.strip():
            raise SystemExit("Provide an email body via --email or stdin.")

        agent = get_agent("imel")
        final_state = run_agent_once(
            agent=agent,
            tenant_id=args.tenant_id,
            input_payload={
                "sender_email": args.sender,
                "email_content": email_content,
            },
            database_url=settings.database_url,
            use_llm=args.use_llm,
        )

        print("\n=== FINAL STATE ===")
        print(json.dumps(final_state, indent=2, default=str))
        return 0

    if args.cmd == "run-kall":
        agent = get_agent("kall")
        final_state = run_agent_once(
            agent=agent,
            tenant_id=args.tenant_id,
            input_payload={
                "ticket_id": args.ticket_id,
                "sender_email": args.sender,
            },
            database_url=settings.database_url,
            use_llm=args.use_llm,
        )

        print("\n=== FINAL STATE ===")
        print(json.dumps(final_state, indent=2, default=str))
        return 0

    raise SystemExit(f"Unknown command: {args.cmd!r}")
