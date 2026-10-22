"""Function tools for sessions, declared as MCP-shaped contracts.

A tool has a name, a description and a JSON Schema for its input, the fields
an MCP server lists (`inputSchema` there), so the same contracts can later be
served by a remote MCP server. Handlers are read-only or record a proposal for the run's own
review, and scope themselves to the run through their context. Every call is
validated against its schema, logged once per session and call ID, bounded in
size, and answered without internal error text: the model reads a short reason
it can act on, never a stack trace. A call that fails leaves only its log: its
handler's writes roll back with it.

A session's own work, such as a bill's proposal, is its final answer instead
(`Answer`): the provider constrains it to the tool's schema, so its shape
cannot be wrong, and it is checked by the same handler once per turn.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from psycopg import Rollback
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


def _refusal(tool, arguments):
    """Why the arguments break the tool's contract, naming each fault where it is; None when they keep it.

    best_match finds the most specific error, but stops at a nullable value whose own schema reports several,
    naming the whole value. A value that is given is held to its non-null schema, so those errors are the cause.
    """
    found = [best_match(Draft202012Validator(tool.input_schema).iter_errors(arguments))]
    if found[0] is None:
        return None
    while found[0].validator == "anyOf" and found[0].context:
        causes = [e for e in found[0].context if not (e.validator == "type" and e.validator_value == "null")]
        if not causes or len(causes) == len(found[0].context):
            break  # not a nullable value: which alternative was meant is not ours to guess
        best = best_match(causes)
        found = [best, *(e for e in causes if e is not best and e.absolute_path == best.absolute_path)]
    where = "/".join(str(part) for part in found[0].absolute_path) or "arguments"
    return f"Invalid {where}: {'; '.join(e.message for e in found[:3])}"[:500]


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
    refusal = _refusal(tool, arguments)
    if refusal is not None:
        return False, refusal
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
    with connection.transaction() as attempt:
        success, text = compute(tools, context, call.name, call.arguments)
        if not success:
            raise Rollback(attempt)
    connection.execute(
        """INSERT INTO tool_calls(tenant_id,item_id,session_id,call_id,turn_id,name,arguments,success,answer,duration_ms)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (item["tenant_id"], item["id"], session_id, call.call_id, call.turn_id,
         call.name if call.name in tools else "unknown", Jsonb(_evidence(call.arguments)), success, text,
         round((time.monotonic() - started) * 1000)))
    return success, text


# Times a session's final answer goes back to it for correcting; the handler settles what is left after that.
CORRECTIONS = 2
# The schema keywords the provider was measured to constrain a final answer with (docs/rebuild/evidence.md).
CONSTRAINED = frozenset({"type", "properties", "required", "additionalProperties", "items", "anyOf", "enum",
                         "description", "pattern", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
                         "minItems", "maxItems"})


@dataclass(frozen=True)
class Answer:
    """A session's final answer: constrained to `tool.input_schema` and checked by `tool.handler` once per turn.

    The model never calls it as a tool. `settled(result)` says whether a checked answer leaves nothing to
    correct; `again` tells the session how to answer once more, after what the check said. A schema the
    provider could not fully constrain is refused here, where the workflow declares it.
    """

    tool: Tool
    settled: Callable[[dict], bool] = lambda result: True
    again: str = "Answer again with the whole answer corrected."

    def __post_init__(self):
        fault = _unconstrained(self.tool.input_schema, "answer")
        if fault:
            raise ValueError(fault)


def _unconstrained(schema, path):
    """Why the provider could not hold an answer to this schema, or None.

    A constrained answer is whole: every property present and nothing else, an absent value written as null, and
    every enum typed. A keyword the provider was not measured to constrain with could be ignored silently.
    """
    unknown = sorted(set(schema) - CONSTRAINED)
    if unknown:
        return f"{path}: {unknown[0]} is not a keyword the provider constrains an answer with"
    if "enum" in schema and "type" not in schema:
        return f"{path}: an enum needs its type"
    if "properties" in schema:
        if schema.get("additionalProperties") is not False:
            return f"{path}: an object must not allow other properties"
        optional = sorted(set(schema["properties"]) - set(schema.get("required", [])))
        if optional:
            return f"{path}: every property must be required, null where it may be absent ({optional[0]} is optional)"
    children = [(f"{path}/{name}", child) for name, child in schema.get("properties", {}).items()]
    children += [(path, child) for child in schema.get("anyOf", [])]
    children += [(path, schema["items"])] if isinstance(schema.get("items"), dict) else []
    return next((fault for child_path, child in children if (fault := _unconstrained(child, child_path))), None)


def conclude(connection, item, session_id, turn_id, text, final, context):
    """Check one turn's final answer once: the correction to send back, or None when the session is done.

    The answer is logged as a call of `final.tool` keyed by its turn, so a turn checked again after a worker
    restart gets its stored verdict. After CORRECTIONS corrections the session ends whatever the verdict.
    The caller commits.
    """
    call = SimpleNamespace(call_id=f"answer:{turn_id}", turn_id=turn_id, name=final.tool.name, arguments=text)
    success, reply = answer(connection, item, session_id, call, {final.tool.name: final.tool}, context)
    if success and final.settled(json.loads(reply)):
        return None
    checked = connection.execute(
        """SELECT count(*) AS n FROM tool_calls WHERE tenant_id=%s AND item_id=%s AND session_id=%s
           AND call_id LIKE 'answer:%%'""", (item["tenant_id"], item["id"], session_id)).fetchone()["n"]
    if checked > CORRECTIONS:
        return None
    return f"Minkops {'checked' if success else 'refused'} this answer: {reply}\n{final.again}"


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
