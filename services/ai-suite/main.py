from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path


def _import_run_imel():
    """Import `run_imel` with a local-dev fallback.

    In a proper install, `agents` is an installed dependency of ai-suite.
    When running this file directly from the repo, Python may not know where the
    `agents/` package is. This fallback adds `agents/src` to `sys.path` so you
    can run a demo without packaging work.
    """

    try:
        from agents.general.imel.graph import run_imel

        return run_imel
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[2]
        agents_src = repo_root / "agents" / "src"
        sys.path.insert(0, str(agents_src))
        from agents.general.imel.graph import run_imel  # type: ignore

        return run_imel


def _read_email_from_stdin() -> str:
    """Read the full email body from stdin."""

    # If stdin is a TTY, there is no piped input.
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description="Demo runner for the Imel email agent.")
    parser.add_argument(
        "--sender",
        default="customer@example.com",
        help="Sender email address (demo metadata).",
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant/workspace id (placeholder until you add a DB).",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Email content as a string. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured LLM (requires LangChain + Ollama). Defaults to heuristic demo mode.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    email_content = args.email if args.email is not None else _read_email_from_stdin()
    if not email_content.strip():
        parser.error("Provide an email via stdin or --email.")

    run_imel = _import_run_imel()

    tenant_brand = {
        # TODO(DB): Load these fields from your tenant configuration table.
        # Tenants can customize brand details only (tone, signature, keywords, etc.).
        "agent_display_name": "Imel",
        "tone": "concise, friendly, and professional",
        "keywords": ["Minkops", "support", "quick resolution"],
        "email_signature": "— Minkops Support Team",
        "brand_kit": {"brand_name": "Minkops.ai"},
    }

    llm = None
    if args.use_llm:
        # If this fails on your machine, just run without `--use-llm` and the
        # agent will use heuristic classification + template replies.
        try:
            from agents.general.imel.tools import get_chat_model

            llm = get_chat_model()
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"Failed to initialize LLM. Re-run without --use-llm. Error: {exc}") from exc

    state = run_imel(
        email_id=str(uuid.uuid4()),
        sender_email=args.sender,
        email_content=email_content,
        tenant_id=args.tenant_id,
        tenant_brand=tenant_brand,
        llm=llm,
    )

    print("\n=== FINAL STATE ===")
    print(json.dumps(state, indent=2, default=str))


if __name__ == "__main__":
    main()
