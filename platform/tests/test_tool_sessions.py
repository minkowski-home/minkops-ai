"""The tool-session driver against a protocol-faithful fake of the Agents API.

What matters is what the provider receives: every pending call answered
exactly once, never a second paid session for one attempt, and failures
reported with the provider's own reason.
"""

import json

import pytest
from fake_agents import USAGE, FakeAgents, Script

from minkops_platform.runtime import openai_hosted
from minkops_platform.runtime.openai_hosted import (
    SessionAbandoned,
    SessionFailed,
    SessionSpec,
    run_tool_session,
)

METADATA = {"minkops_item": "item-1", "minkops_attempt": "1"}
LOOKUPS = [("find_ledger", {"subjects": ["Acme Steel"]}), ("find_ledger", {"subjects": ["Freight"]})]
PROPOSE = [("propose", {"amount": "1180.00"})]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(openai_hosted.time, "sleep", lambda seconds: None)


def spec(metadata=METADATA):
    return SessionSpec(model="gpt-6-luna", instructions="Enter the bill.", tools=[],
                       content=[{"type": "input_text", "text": "Bill 1"}], metadata=metadata)


class Worker:
    """The callbacks a lane gives the driver, with answers stored per call ID."""

    def __init__(self, store=None, *, stop_after=None, leave_after=None):
        self.store = {} if store is None else store
        self.computed, self.ids = [], []
        self.stop_after, self.leave_after = stop_after, leave_after

    def answer(self, call):
        if call.call_id not in self.store:
            self.computed.append(call.call_id)
            self.store[call.call_id] = (True, json.dumps({"call": call.name, "n": len(self.store)}))
        return self.store[call.call_id]

    def saved(self, session_id, turn_id):
        self.ids.append((session_id, turn_id))

    def requesting(self):
        return 1_800_000_000

    def alive(self):
        if self.leave_after is not None and len(self.computed) >= self.leave_after:
            raise LookupError("lease lost")
        return self.stop_after is None or len(self.computed) < self.stop_after

    def run(self, client, **resume):
        return run_tool_session(spec(), answer=self.answer, saved=self.saved, requesting=self.requesting,
                                alive=self.alive, client=client, **resume)


def sent(session):
    return [(answer["name"], answer["success"]) for answer in session.answers]


def test_each_pending_call_is_answered_once_and_the_turn_usage_is_returned():
    fake = FakeAgents(Script(LOOKUPS, PROPOSE, usage_on_event=True))
    worker = Worker()
    result = worker.run(fake)
    [session] = fake.sessions
    assert sent(session) == [("find_ledger", True), ("find_ledger", True), ("propose", True)]
    assert session.content == [{"type": "input_text", "text": "Bill 1"}] and session.metadata == METADATA
    # Provider IDs are persisted as soon as they exist, before any answer.
    assert worker.ids[:2] == [(session.id, None), (session.id, session.turn.id)]
    assert result == {"session_id": session.id, "turn_id": session.turn.id, "usage": USAGE}
    # The driver stopped at idle: it never waited on a stream with nothing coming.
    assert (fake.streams, fake.waits) == (1, 0)


# Events: 1 created, 2 turn.created, 3 in_progress, 4-5 the two lookups, 6 requires_action,
# 7 propose, 8 requires_action, 9 the reply, 10 turn.completed, 11 idle.
@pytest.mark.parametrize(("drop_after", "streams"), [(2, 2), (6, 2), (9, 1)],
                         ids=["before-any-call", "after-answering", "turn-ends-detached"])
def test_a_dropped_stream_reattaches_without_answering_any_call_twice(drop_after, streams):
    fake = FakeAgents(Script(LOOKUPS, PROPOSE))
    fake.drops = [drop_after]
    worker = Worker()
    worker.run(fake)
    [session] = fake.sessions
    assert sent(session) == [("find_ledger", True), ("find_ledger", True), ("propose", True)]
    # A turn that ended while detached is read from the session, not streamed again.
    assert len(worker.computed) == 3 and fake.streams == streams and fake.resent == 0


def test_a_resumed_session_answers_only_what_is_pending_and_starts_no_other_session():
    fake = FakeAgents(Script(LOOKUPS, PROPOSE))
    store = {}
    first = Worker(store, leave_after=2)
    with pytest.raises(LookupError):
        first.run(fake)
    [session] = fake.sessions
    assert session.status == "requires_action" and fake.cancels == 0  # left running for a successor
    second = Worker(store)
    result = second.run(fake, session_id=session.id)
    assert len(fake.store) == 1 and result["session_id"] == session.id
    # The replayed round-one calls are not answered again: the provider would accept
    # a repeated answer silently. Only round two is computed and sent.
    assert sent(session) == [("find_ledger", True), ("find_ledger", True), ("propose", True)]
    assert len(second.computed) == 1 and fake.resent == 0


def test_a_lost_creation_response_is_recovered_without_a_second_session():
    fake = FakeAgents(Script(PROPOSE))
    fake.lose_creation = 1
    result = Worker().run(fake)
    [session] = fake.sessions
    assert result["session_id"] == session.id and sent(session) == [("propose", True)]


def test_a_restarted_creation_finds_its_session_by_metadata_among_newer_ones():
    fake = FakeAgents(Script(PROPOSE))
    api = fake.beta.agents.sessions
    agent = {"model": "gpt-6-luna", "instructions": "x", "tools": []}
    content = [{"role": "user", "content": []}]
    api.create(agent=agent, environment={"type": "none"}, metadata=METADATA, input=content, stream=True)
    mine = fake.sessions[0]
    api.create(agent=agent, environment={"type": "none"}, metadata={**METADATA, "minkops_attempt": "2"},
               input=content, stream=True)
    result = Worker().run(fake, requested_at=mine.created_at)
    assert result["session_id"] == mine.id and len(fake.store) == 2
    assert sent(mine) == [("propose", True)]


def test_a_failed_turn_reports_the_provider_code():
    fake = FakeAgents(Script(PROPOSE, ending="failed", error_code="server_overloaded"))
    with pytest.raises(SessionFailed) as failure:
        Worker().run(fake)
    assert failure.value.code == "server_overloaded" and failure.value.transient


def test_stopping_cancels_the_turn():
    fake = FakeAgents(Script(LOOKUPS, PROPOSE))
    with pytest.raises(SessionAbandoned):
        Worker(stop_after=2).run(fake)
    [session] = fake.sessions
    assert fake.cancels == 1 and session.turn.status == "cancelled"


def test_a_call_not_yet_registered_is_answered_once_on_retry():
    fake = FakeAgents(Script(PROPOSE))
    fake.unregistered_once = True
    Worker().run(fake)
    assert sent(fake.sessions[0]) == [("propose", True)]


# --- constrained final answers --------------------------------------------------------

ANSWER = {"type": "object", "additionalProperties": False, "required": ["amount"],
          "properties": {"amount": {"type": "string"}}}


class Checker:
    """The lane's `final` callback: each turn's answer checked once, a correction for the first."""

    def __init__(self, corrections=("The bill total is 1,280.00.",), leave_once=False):
        self.corrections, self.leave_once = list(corrections), leave_once
        self.checked, self.verdicts = [], {}

    def final(self, turn_id, text):
        if self.leave_once:
            self.leave_once = False
            raise LookupError("lease lost")
        self.checked.append((turn_id, json.loads(text)))
        if turn_id not in self.verdicts:  # a repeated turn gets the stored verdict, as tools.conclude gives
            self.verdicts[turn_id] = self.corrections.pop(0) if self.corrections else None
        return self.verdicts[turn_id]


def answered(fake, checker, **resume):
    worker = Worker()
    lookup = {"type": "function", "name": "find_ledger", "description": "Find ledgers.", "parameters": {}}
    result = run_tool_session(SessionSpec(**{**spec().__dict__, "tools": [lookup], "answer_schema": ANSWER}),
                              answer=worker.answer,
                              saved=worker.saved, requesting=worker.requesting, alive=worker.alive, client=fake,
                              final=checker.final, **resume)
    return result, worker


def test_a_session_runs_at_its_reasoning_effort_and_service_tier():
    fake = FakeAgents(Script(PROPOSE))
    worker = Worker()
    run_tool_session(SessionSpec(**{**spec().__dict__, "reasoning": {"effort": "high"}, "service_tier": "fast"}),
                     answer=worker.answer, saved=worker.saved, requesting=worker.requesting, alive=worker.alive,
                     client=fake)
    [session] = fake.sessions
    assert (session.agent["reasoning"], session.agent["service_tier"]) == ({"effort": "high"}, "fast")


def test_a_constrained_session_ends_on_a_settled_final_answer():
    fake = FakeAgents(Script(LOOKUPS, answers=[{"amount": "1180.00"}], usage_on_event=True))
    checker = Checker(corrections=())
    result, worker = answered(fake, checker)
    [session] = fake.sessions
    # The provider constrains the final answer to the schema; the answer is no tool the model can call.
    assert session.agent["text"] == {"format": {"type": "json_schema", "schema": ANSWER}}
    assert sent(session) == [("find_ledger", True), ("find_ledger", True)]
    assert checker.checked == [(session.turn.id, {"amount": "1180.00"})] and session.messages == []
    assert result == {"session_id": session.id, "turn_id": session.turn.id, "usage": USAGE}


def test_an_answer_that_needs_correcting_is_answered_again_in_the_same_session():
    fake = FakeAgents(Script(LOOKUPS, answers=[{"amount": "1180.00"}, {"amount": "1280.00"}], usage_on_event=True))
    checker = Checker()
    result, _ = answered(fake, checker)
    [session] = fake.sessions
    first, second = session.turns
    assert session.messages == ["The bill total is 1,280.00."]
    assert checker.checked == [(first.id, {"amount": "1180.00"}), (second.id, {"amount": "1280.00"})]
    # One paid session; its usage counts every turn.
    assert len(fake.created) == 1 and result["turn_id"] == second.id
    assert result["usage"]["output_tokens"] == 2 * USAGE["output_tokens"]
    assert result["usage"]["input_tokens_details"]["cached_tokens"] == 2 * USAGE["input_tokens_details"]["cached_tokens"]


# Events: 1 created, 2 turn.created, 3 in_progress, 4-5 lookups, 6 requires_action, 7 the answer,
# 8 turn.completed, 9 idle: the first turn ends with the stream detached.
def test_a_correction_sent_while_detached_is_sent_once():
    fake = FakeAgents(Script(LOOKUPS, answers=[{"amount": "1180.00"}, {"amount": "1280.00"}]))
    fake.drops = [8, 9]
    checker = Checker()
    answered(fake, checker)
    [session] = fake.sessions
    assert session.messages == ["The bill total is 1,280.00."] and len(session.turns) == 2
    assert [turn for turn, _ in checker.checked].count(session.turns[0].id) >= 1


def test_an_answer_a_departed_worker_left_unchecked_is_checked_by_its_successor():
    fake = FakeAgents(Script(LOOKUPS, answers=[{"amount": "1180.00"}]))
    checker = Checker(corrections=(), leave_once=True)
    with pytest.raises(LookupError):
        answered(fake, checker)
    [session] = fake.sessions
    assert session.status == "idle" and checker.checked == []
    result, _ = answered(fake, checker, session_id=session.id)
    assert checker.checked == [(session.turn.id, {"amount": "1180.00"})] and len(fake.created) == 1
    assert result["turn_id"] == session.turn.id
