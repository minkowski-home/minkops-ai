"""Function-tool contracts: what the model is told, and what is logged once per call."""

import json
import logging
import os
from types import SimpleNamespace

import pytest

from minkops_platform import work
from minkops_platform.runtime import tools
from minkops_platform.runtime.tools import Tool, ToolError

SUBJECTS = {"type": "object", "properties": {"subjects": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
            "required": ["subjects"], "additionalProperties": False}
ran = []


def find_ledger(context, arguments):
    ran.append(arguments)
    if arguments["subjects"] == ["Unknown"]:
        raise ToolError("No ledger matches Unknown. Ask for the party's GSTIN instead.")
    if arguments["subjects"] == ["boom"]:
        raise RuntimeError("connection to db-host failed: password=hunter2")
    if arguments["subjects"] == ["everything"]:
        return {"ledgers": ["x" * 1000] * 100}
    return {"ledgers": [{"name": subject, "group": "Sundry Creditors"} for subject in arguments["subjects"]]}


# A nullable nested object, as a proposal's voucher is: an error inside it must be named, not the whole value.
ENTRY = {"type": "object", "required": ["entry"], "additionalProperties": False, "properties": {"entry": {"anyOf": [
    {"type": "null"}, {"type": "object", "required": ["lines"], "additionalProperties": False, "properties": {
        "lines": {"type": "array", "items": {"type": "object", "required": ["tds"], "properties": {
            "tds": {"type": ["object", "null"]}}}}}}]}}}
TOOLS = {"find_ledger": Tool("find_ledger", "Find ledgers by name.", SUBJECTS, find_ledger),
         "record": Tool("record", "Record an entry.", ENTRY, lambda context, arguments: ran.append(arguments) or {})}


@pytest.mark.parametrize(("name", "arguments", "expected"), [
    ("find_ledger", {"subjects": ["Acme"]}, (True, '{"ledgers":[{"name":"Acme","group":"Sundry Creditors"}]}')),
    ("find_ledger", '{"subjects": ["Acme"]}', (True, '{"ledgers":[{"name":"Acme","group":"Sundry Creditors"}]}')),
    ("find_party", {"subjects": ["Acme"]}, (False, "There is no tool named find_party.")),
    ("find_ledger", "{not json", (False, "Arguments must be a JSON object.")),
    ("find_ledger", ["Acme"], (False, "Arguments must be a JSON object.")),
    ("find_ledger", {"subjects": []}, (False, "Invalid subjects: [] should be non-empty")),
    ("find_ledger", {"subjects": ["Acme"], "all": True}, (False, "Invalid arguments: Additional properties are not "
                                                                 "allowed ('all' was unexpected)")),
    ("find_ledger", {"subjects": ["Unknown"]}, (False, "No ledger matches Unknown. Ask for the party's GSTIN instead.")),
    ("find_ledger", {"subjects": ["everything"]}, (False, "The answer is too large. Ask about fewer subjects at a time.")),
    ("record", {"entry": {"lines": [{"amount": 1}]}}, (False, "Invalid entry/lines/0: 'tds' is a required property")),
], ids=["answer", "json-text", "unknown-tool", "bad-json", "not-an-object", "schema", "extra-field", "refusal",
        "too-large", "nested"])
def test_the_model_is_told_exactly_why_a_call_was_refused(name, arguments, expected):
    ran.clear()
    assert tools.compute(TOOLS, None, name, arguments) == expected
    # A call that breaks its contract never reaches the handler.
    assert bool(ran) == (expected[0] or "No ledger" in expected[1] or "too large" in expected[1])


def test_an_internal_failure_is_logged_but_never_shown_to_the_model(caplog):
    with caplog.at_level(logging.ERROR, logger="minkops_platform.runtime.tools"):
        success, text = tools.compute(TOOLS, None, "find_ledger", {"subjects": ["boom"]})
    assert not success and "hunter2" not in text and "db-host" not in text
    assert "hunter2" in caplog.text  # the operator still sees the cause


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
def test_a_repeated_call_gets_its_logged_answer_without_running_again():
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        operator = factory.user(db, tenant, role="admin")
        run = factory.run(db, tenant, factory.client(db, tenant), factory.workflow(db, tenant), operator,
                          [work.ItemSpec("bill", {"file_id": "a"})])
        item = db.execute("SELECT * FROM run_items WHERE run_id=%s", (run["id"],)).fetchone()
        call = SimpleNamespace(call_id="call_1", turn_id="turn_1", name="find_ledger",
                               arguments=json.dumps({"subjects": ["Acme"]}))
        ran.clear()
        first = tools.answer(db, item, "sess_1", call, TOOLS, None)
        again = tools.answer(db, item, "sess_1", call, TOOLS, None)
        assert first == again and first[0] and len(ran) == 1
        # A call with arguments the model garbled is still evidence: logged, refused, never run.
        garbled = SimpleNamespace(call_id="call_2", turn_id="turn_1", name="drop_table", arguments="{oops")
        assert tools.answer(db, item, "sess_1", garbled, TOOLS, None) == (False, "There is no tool named drop_table.")
        logged = db.execute("SELECT call_id,name,arguments,success FROM tool_calls WHERE item_id=%s ORDER BY call_id",
                            (item["id"],)).fetchall()
        assert [(r["call_id"], r["name"], r["arguments"], r["success"]) for r in logged] == [
            ("call_1", "find_ledger", {"subjects": ["Acme"]}, True),
            ("call_2", "unknown", {"unparsed": "{oops"}, False)]
