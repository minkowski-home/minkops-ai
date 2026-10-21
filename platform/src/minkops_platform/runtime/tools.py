"""Function tools for sessions, declared as MCP-shaped contracts.

A tool has a name, a description and a JSON Schema for its input, the fields
an MCP server lists (`inputSchema` there), so the same contracts can later be
served by a remote MCP server. Handlers are read-only or record a proposal for the run's own
review, and scope themselves to the run through their context. Every call is
validated against its schema, logged once per session and call ID, bounded in
size, and answered without internal error text: the model reads a short reason
it can act on, never a stack trace.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)
ANSWER_LIMIT = 64_000
ARGUMENTS_LIMIT = 16_000


class ToolError(Exception):
    """A refusal written for the model to read and act on."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[object, dict], dict]

    def __post_init__(self):
        Draft202012Validator.check_schema(self.input_schema)

    def function(self):
        """The OpenAI function-tool declaration."""
        return {"type": "function", "name": self.name, "description": self.description,
                "parameters": self.input_schema}


def compute(tools, context, name, arguments):
    """(success, answer text) for one call."""
    tool = tools.get(name)
    if tool is None:
        return False, f"There is no tool named {name}."
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return False, "Arguments must be a JSON object."
    if not isinstance(arguments, dict):
        return False, "Arguments must be a JSON object."
    error = next(iter(sorted(Draft202012Validator(tool.input_schema).iter_errors(arguments),
                             key=lambda e: list(e.absolute_path))), None)
    if error is not None:
        where = "/".join(str(part) for part in error.absolute_path) or "arguments"
        return False, f"Invalid {where}: {error.message}"[:500]
    try:
        result = tool.handler(context, arguments)
    except ToolError as refusal:
        return False, str(refusal)[:1000]
    except Exception:
        log.exception("Tool %s failed", name)
        return False, "The tool could not answer this time. Try again with a narrower request."
    answer = json.dumps(result, default=str, separators=(",", ":"), ensure_ascii=False)
    if len(answer) > ANSWER_LIMIT:
        return False, "The answer is too large. Ask about fewer subjects at a time."
    return True, answer


def answer(connection, item, session_id, call, tools, context):
    """Answer a call once per session: a repeated call ID gets the logged answer.

    `call` has `call_id`, `turn_id`, `name` and `arguments`. The caller commits.
    """
    # Scoped to the item as well: an answer is never served across items or tenants.
    stored = connection.execute(
        "SELECT success,answer FROM tool_calls WHERE tenant_id=%s AND item_id=%s AND session_id=%s AND call_id=%s",
        (item["tenant_id"], item["id"], session_id, call.call_id)).fetchone()
    if stored:
        return stored["success"], stored["answer"]
    started = time.monotonic()
    success, text = compute(tools, context, call.name, call.arguments)
    connection.execute(
        """INSERT INTO tool_calls(tenant_id,item_id,session_id,call_id,turn_id,name,arguments,success,answer,duration_ms)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (item["tenant_id"], item["id"], session_id, call.call_id, call.turn_id,
         call.name if call.name in tools else "unknown", Jsonb(_evidence(call.arguments)), success, text,
         round((time.monotonic() - started) * 1000)))
    return success, text


def _evidence(arguments):
    """The arguments as logged: parsed when they are a JSON object, bounded either way."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return {"unparsed": arguments[:2000]}
    text = json.dumps(arguments, ensure_ascii=False)
    if not isinstance(arguments, dict) or len(text) > ARGUMENTS_LIMIT:
        return {"unparsed": text[:2000]}
    return arguments
