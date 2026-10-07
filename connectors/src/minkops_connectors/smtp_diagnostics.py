"""No-message connectivity check for the Workspace SMTP relay."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass

import aiosmtplib
from .workspace_smtp import SMTP_HOSTS


@dataclass(frozen=True)
class DiagnosticResult:
    phase: str
    error_class: str | None = None
    response_code: int | None = None
    reason_category: str | None = None


def _response_code(error: Exception) -> int | None:
    code = getattr(error, "code", None)
    return code if isinstance(code, int) and 100 <= code <= 599 else None


def _reason_category(error: Exception, code: int | None) -> str:
    """Map private provider text to a small safe enum; never return the text."""

    reason = str(error).lower()
    if type(error).__name__ == "SMTPAuthenticationError":
        return "authentication_rejected"
    if any(term in reason for term in ("try again later", "server busy", "service isn't available")):
        return "temporary_service_unavailable"
    if any(term in reason for term in ("relay denied", "not authorized", "not registered")):
        return "relay_policy_rejected"
    if any(term in reason for term in ("invalid credentials", "authentication failed")):
        return "authentication_rejected"
    if code is not None and 400 <= code < 500:
        return "temporary_smtp_failure"
    if code is not None and 500 <= code < 600:
        return "permanent_smtp_failure"
    return "unknown_smtp_failure"


async def check_relay() -> DiagnosticResult:
    """Connect, negotiate TLS, and authenticate without sending a message."""

    host = os.getenv("SMTP_HOST", "").strip().lower()
    port = os.getenv("SMTP_PORT", "").strip()
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if host not in SMTP_HOSTS or port != "587" or not username or not password:
        return DiagnosticResult("configuration", "ConfigurationMissing")

    client = aiosmtplib.SMTP(
        hostname=host,
        port=587,
        local_hostname="minkops.com",
        start_tls=True,
        timeout=8,
    )
    connected = False
    try:
        try:
            await client.connect()
            connected = True
        except Exception as exc:
            code = _response_code(exc)
            return DiagnosticResult(
                "connect_or_tls", type(exc).__name__, code, _reason_category(exc, code)
            )
        try:
            await client.login(username, password)
        except Exception as exc:
            code = _response_code(exc)
            return DiagnosticResult(
                "authentication", type(exc).__name__, code, _reason_category(exc, code)
            )
        return DiagnosticResult("authenticated", None, None)
    finally:
        if connected:
            try:
                await client.quit()
            except Exception:
                pass


async def _main() -> int:
    result = await check_relay()
    print(
        f"SMTP_PREFLIGHT phase={result.phase} error_class={result.error_class or 'none'} "
        f"response_code={result.response_code or 'none'} "
        f"reason_category={result.reason_category or 'none'}"
    )
    return 0 if result.phase == "authenticated" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
