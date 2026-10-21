"""A protocol-faithful stand-in for the Agents API sessions resource.

It behaves as the live API was measured to (docs/rebuild/evidence.md): a
conversation-only session is created with its input and starts its turn at
once; a call is registered as pending exactly when the session reports
requires_action; every new stream replays the session's events from the
start; creation is not idempotent; listed sessions carry their metadata.

Each session follows a script: rounds of function calls, each round issued
together and answered before the next, then an ending. Tests inject faults:
dropped streams, a lost creation response and a call-registration race.
"""

import itertools
import json
import threading
from types import SimpleNamespace as Obj

import httpx2
from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, NotFoundError

_IDS = itertools.count(1)
_REQUEST = httpx2.Request("POST", "https://api.openai.test/v1/agents/sessions")
USAGE = {"input_tokens": 900, "input_tokens_details": {"cached_tokens": 600}, "output_tokens": 40,
         "output_tokens_details": {"reasoning_tokens": 10}, "total_tokens": 940}


class Usage(Obj):
    def model_dump(self):
        return dict(self.__dict__)


class Script:
    """What the model does: rounds of (tool name, arguments) calls, then an ending.

    A round may be a callable that receives the answers so far and the session
    (its content included) and returns the next round's calls, so a test can
    script a model that reacts to what it was given and told.
    """

    def __init__(self, *rounds, ending="completed", error_code=None, usage_on_event=False, usage_after=0):
        self.rounds, self.ending, self.error_code = list(rounds), ending, error_code
        # As measured live, the end of a turn usually carries no usage; the turn
        # reports it a few seconds later (here: after `usage_after` reads).
        self.usage_on_event, self.usage_after = usage_on_event, usage_after


def _error(status, message):
    response = httpx2.Response(status, request=_REQUEST)
    body = {"type": "invalid_request_error", "code": "invalid_request_error", "message": message}
    return (BadRequestError if status == 400 else NotFoundError)(message, response=response, body=body)


class _Session:
    def __init__(self, fake, metadata, script, agent, content, created_at):
        self.fake, self.metadata, self.script, self.agent, self.content = fake, metadata, script, agent, content
        self.id = f"sess_{next(fake.ids)}"
        self.created_at, self.status, self.error = created_at, "in_progress", None
        self.log, self.pending, self.answers, self.answered_ids = [], {}, [], set()
        self.usage, self.reads = None, 0
        self.round = 0
        self.turn = Obj(id=f"turn_{next(fake.ids)}", session_id=self.id, status="in_progress", subagent_id=None,
                       created_at=created_at, usage=None, error=None)

    def snapshot(self):
        return Obj(id=self.id, status=self.status, required_actions=list(self.pending.values()),
                  metadata=dict(self.metadata), error=self.error, created_at=self.created_at, usage=None)

    def emit(self, kind, **fields):
        self.log.append(Obj(type=kind, event_id=f"evt_{next(self.fake.ids)}", **fields))

    def turn_event(self, kind, **fields):
        turn = Obj(**self.turn.__dict__)
        self.emit(kind, session_id=self.id, turn_id=self.turn.id, turn=turn, **fields)

    def start(self):
        self.emit("agent.session.created", session=self.snapshot())
        self.turn_event("agent.session.turn.created")
        self.emit("agent.session.in_progress", session=self.snapshot())
        self.advance()

    def advance(self):
        if self.round < len(self.script.rounds):
            calls = self.script.rounds[self.round]
            calls = calls(list(self.answers), self) if callable(calls) else calls
            if calls:
                for name, arguments in calls:
                    call = Obj(type="function_call", call_id=f"call_{next(self.fake.ids)}", turn_id=self.turn.id,
                              name=name, arguments=json.dumps(arguments))
                    self.turn_event("agent.session.turn.item.added", item=call)
                    self.pending[call.call_id] = call
                self.status = "requires_action"
                self.emit("agent.session.requires_action", session=self.snapshot())
                return
        self.turn_event("agent.session.turn.item.added",
                        item=Obj(type="message", content=[Obj(type="output_text", text="DONE")]))
        self.end(self.script.ending)

    def end(self, status):
        usage = Usage(**USAGE)
        self.turn.status, self.usage, self.reads = status, usage, 0
        if status == "failed":
            self.turn.error = Obj(code=self.script.error_code, message=f"The turn failed ({self.script.error_code}).")
        self.pending.clear()
        if status == "failed":
            # The live stream reports a failure as an error event, which the SDK raises.
            self.emit("error", session_id=self.id, message=self.turn.error.message)
        self.turn_event(f"agent.session.turn.{status}", usage=usage if self.script.usage_on_event else None)
        self.status = "idle"
        self.emit("agent.session.idle", session=self.snapshot())

    def answer(self, result):
        call = self.pending.get(result["call_id"])
        if call is None and result["call_id"] in self.answered_ids:
            self.fake.resent += 1  # accepted and ignored, as the live API does
            return
        if call is None or self.fake.unregistered_once:
            self.fake.unregistered_once = False
            raise _error(400, f"Unknown pending tool call: {result['call_id']}")
        self.answered_ids.add(call.call_id)
        del self.pending[result["call_id"]]
        self.answers.append({"name": call.name, "arguments": json.loads(call.arguments), "success": result["success"],
                             "text": result.get("output") if result["success"] else result.get("error")})
        if not self.pending:
            self.round += 1
            self.status = "in_progress"
            self.advance()


class _Stream:
    def __init__(self, fake, session):
        self.fake, self.session = fake, session
        self.drop_after = fake.drops.pop(0) if fake.drops else None
        self.closed = False
        fake.streams += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def __iter__(self):
        index = 0
        while not self.closed:
            if self.drop_after is not None and index >= self.drop_after:
                raise APIConnectionError(request=_REQUEST)
            if index >= len(self.session.log):
                # A live stream would wait here for events that are not coming.
                self.fake.waits += 1
                raise APITimeoutError(_REQUEST)
            event = self.session.log[index]
            index += 1
            if event.type == "error":
                raise APIError(event.message, _REQUEST, body={"message": event.message})
            yield event


class _Events:
    def __init__(self, fake):
        self.fake = fake

    def create(self, session_id, *, events, idempotency_key=None):
        with self.fake.lock:
            return self._create(session_id, events, idempotency_key)

    def _create(self, session_id, events, idempotency_key):
        session = self.fake.get(session_id)
        for event in events:
            if event["type"] == "agent.session.input.tool_result":
                session.answer(event)
            elif event["type"] == "agent.session.input.cancel":
                self.fake.cancels += 1
                if session.turn.status in ("in_progress", "waiting"):
                    session.end("cancelled")
        return None

    def stream(self, session_id):
        return _Stream(self.fake, self.fake.get(session_id))


class _Turns:
    def __init__(self, fake):
        self.fake = fake

    def list(self, session_id):
        return [self.retrieve(self.fake.get(session_id).turn.id, session_id=session_id)]

    def retrieve(self, turn_id, *, session_id):
        session = self.fake.get(session_id)
        assert session.turn.id == turn_id
        session.reads += 1
        reported = session.usage if session.usage and session.reads > session.script.usage_after else None
        return Obj(**{**session.turn.__dict__, "usage": reported})


class _Sessions:
    def __init__(self, fake):
        self.fake, self.events, self.turns = fake, _Events(fake), _Turns(fake)

    def create(self, *, agent, environment, metadata, input, stream):
        assert environment == {"type": "none"} and stream is True
        assert all(isinstance(value, str) for value in metadata.values())
        with self.fake.lock:
            self.fake.clock += 1
            content = input[0]["content"]
            if self.fake.script_for:
                script = self.fake.script_for(metadata, content)
            else:
                script = self.fake.scripts.pop(0) if len(self.fake.scripts) > 1 else self.fake.scripts[0]
            session = _Session(self.fake, metadata, script, agent, content, self.fake.clock)
            self.fake.store[session.id] = session
            self.fake.created.append(session)
            session.start()
        if self.fake.lose_creation:
            self.fake.lose_creation -= 1
            raise APIConnectionError(request=_REQUEST)
        return _Stream(self.fake, session)

    def retrieve(self, session_id):
        return self.fake.get(session_id).snapshot()

    def list(self, *, order, limit):
        assert order == "desc" and limit <= 100
        return [s.snapshot() for s in sorted(self.fake.store.values(), key=lambda s: s.created_at, reverse=True)]

    def delete(self, session_id):
        self.fake.get(session_id)
        del self.fake.store[session_id]


class FakeAgents:
    """Pass as `client`: it serves `client.beta.agents.sessions`.

    Sessions take the given scripts in creation order, the last one repeating,
    or ask `script_for(metadata, content)` when sessions start concurrently.
    """

    def __init__(self, *scripts, script_for=None):
        self.scripts, self.script_for = list(scripts) or [Script()], script_for
        self.lock = threading.RLock()
        # Unique across fakes, like provider IDs, because tool calls are logged by them.
        self.ids = _IDS
        self.clock = 1_800_000_000
        self.store, self.created = {}, []
        self.drops = []  # each new stream drops after this many events
        self.lose_creation = 0
        self.unregistered_once = False
        self.resent = 0
        self.streams = self.waits = self.cancels = 0
        self.beta = Obj(agents=Obj(sessions=_Sessions(self)))

    def get(self, session_id):
        if session_id not in self.store:
            raise _error(404, f"No session found with id '{session_id}'.")
        return self.store[session_id]

    @property
    def sessions(self):
        return sorted(self.store.values(), key=lambda s: s.created_at)
