"""Agent-facing knowledge-base tool contracts (no runtime KB code).

This module defines *interfaces* ("ports") for KB retrieval and tenant profile
loading. Concrete implementations that talk to pgvector/embeddings providers
belong in the runtime service layer (currently `services/ai-suite`).

Keeping this module dependency-free ensures `agents/` remains importable in
minimal environments (unit tests, offline dev) without Postgres drivers or
provider SDKs installed.
"""

from __future__ import annotations

import typing

from .schemas import KBChunk, TenantProfile


class AgentsKB(typing.Protocol):
    """Knowledge-base capabilities an agent may request."""

    def lookup_company_kb(
        self, *, tenant_id: str | None, query: str, top_k: int = 5
    ) -> list[KBChunk]:
        """Retrieve tenant-scoped KB chunks relevant to a query."""

    def load_tenant_profile(self, *, tenant_id: str | None) -> TenantProfile | None:
        """Load tenant branding/profile values (often from a KB brand-kit chunk)."""


def _moved_error() -> RuntimeError:
    """Consistent error for deprecated direct KB calls from `agents/`."""

    return RuntimeError(
        "Direct KB access has moved to the service/orchestrator layer. "
        "Inject a concrete KB implementation (e.g., `services/ai-suite`) "
        "into your graph runner instead of calling `agents.shared.kb` functions."
    )


# Backwards-compatibility shims: these names used to be concrete functions.
def lookup_company_kb(*args, **kwargs):  # pragma: no cover - compatibility shim
    raise _moved_error()


def load_tenant_profile(*args, **kwargs):  # pragma: no cover - compatibility shim
    raise _moved_error()
