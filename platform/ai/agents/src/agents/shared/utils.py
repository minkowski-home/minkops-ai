"""
This module contains shared utilities and general helper functions used by the agents, like logging, error handling, etc.
"""

import datetime
import json
import typing

def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

def safe_json_extract(text: str) -> dict[str, typing.Any]:
    """Best-effort JSON extraction from an LLM response.

    Args:
        text: LLM response text, possibly containing JSON in markdown fences.

    Returns:
        Parsed JSON object.

    Raises:
        json.JSONDecodeError: If no valid JSON object can be extracted.
    """

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Common pattern: the model wraps JSON in markdown fences.
        if "```" in text:
            stripped = text.replace("```json", "```").strip()
            parts = stripped.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("{") and part.endswith("}"):
                    return json.loads(part)
        raise