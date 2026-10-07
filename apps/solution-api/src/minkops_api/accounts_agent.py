"""Compatibility imports; Accounts execution lives in minkops_platform."""

from minkops_platform.accounts.agent import (
    MODEL,
    bill_prompt,
    close_session,
    discovery_prompt,
    execute,
    read_result,
)

__all__ = ["MODEL", "bill_prompt", "close_session", "discovery_prompt", "execute", "read_result"]
