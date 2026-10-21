"""Tool sessions on the OpenAI Agents API: one turn per item, its function calls answered exactly once."""

import time
from contextlib import suppress
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)


def close_session(session_id, *, client=None):
    """Delete a finished session at the provider once its outcome is durably stored."""
    # An earlier cleanup may have succeeded before its receipt was saved.
    with suppress(NotFoundError):
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.delete(session_id)


def cancel_turn(session_id, turn_id=None, *, client=None):
    """Cancel a turn at the provider; closing the event stream alone would leave it running."""
    client = client or OpenAI(timeout=15, max_retries=0)
    with suppress(NotFoundError):
        if turn_id and client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id).status in (
                "completed", "failed", "cancelled"):
            return
        client.beta.agents.sessions.events.create(session_id, events=[{"type": "agent.session.input.cancel"}])


# --- Tool sessions ---------------------------------------------------------------
# Bills and statement chunks run without an execution environment: the model
# reads the content it is given and works only through function tools. The
# worker answers exactly the calls a session lists as pending at that moment:
# never one the provider has not registered, and never one already answered,
# because the provider accepts a repeated answer silently. A dropped stream is
# re-attached. A conversation-only session must be created together with its
# input and creation is not idempotent, so a creation whose response was lost
# is found again by its metadata instead of being started twice.

# Seconds a stream may stay silent before it is re-attached, and the pause before each re-attachment.
TOOL_TIMEOUT = 120
REATTACH_DELAY = 2
# Consecutive attachments that delivered nothing new before the session is given up.
REATTACHMENTS = 5
# Provider and database clocks differ; a lost creation is searched for this far back.
CLOCK_SKEW = 300
# Sessions scanned, newest first, for a lost creation.
SEARCH_LIMIT = 500
# Turn failures worth a new attempt; any other code needs a person.
TRANSIENT = frozenset({"rate_limit_exceeded", "server_overloaded", "server_error", "connection_failed",
                       "request_timeout", "internal_error"})


class SessionFailed(Exception):
    """The provider ended the turn or the session without completing it."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

    @property
    def transient(self):
        return self.code in TRANSIENT


class SessionAbandoned(Exception):
    """The caller asked to stop, and the turn was cancelled."""


@dataclass(frozen=True)
class SessionSpec:
    model: str
    instructions: str
    tools: list
    # The user message's content parts: input_text and input_image items.
    content: list
    # String values that identify this attempt, so a lost creation can be found.
    metadata: dict
    reasoning: dict | None = None


def run_tool_session(spec, *, answer, saved, requesting, alive, client=None, session_id=None, requested_at=None):
    """Run a session's single turn to its end, answering its function calls.

    `answer(call)` returns (success, text) and must return the same answer for
    a repeated call ID. `saved(session_id, turn_id)` persists provider IDs as
    soon as they exist; `requesting()` durably records that a session is about
    to be created and returns that Unix time. `alive()` returns False to cancel
    the turn; an exception it raises leaves the session running for another
    worker to resume. Pass a saved `session_id` to resume that session, or the
    `requested_at` of an earlier creation whose response may have been lost.
    Returns the session ID, the turn ID and the turn's token usage when the
    provider reported it with the turn's end (None otherwise).
    """
    client = client or OpenAI(timeout=TOOL_TIMEOUT, max_retries=0)
    return _ToolSession(client, spec, answer, saved, requesting, alive, session_id, requested_at).run()


class _ToolSession:
    def __init__(self, client, spec, answer, saved, requesting, alive, session_id, requested_at):
        self.client, self.api = client, client.beta.agents.sessions
        self.spec, self.answer, self.saved, self.requesting, self.alive = spec, answer, saved, requesting, alive
        self.id, self.requested_at = session_id, requested_at
        self.turn_id = self.usage = None
        self.ended = self.finished = False
        self.answered, self.seen = set(), set()

    def run(self):
        stalls = 0
        while True:
            self._check()
            progressed = False
            try:
                events = self._attach()
                if events is None:
                    break
                progressed = self._follow(events)
                if self.finished:
                    break
            except (APIConnectionError, InternalServerError, RateLimitError):
                # Transient: attach again. A creation that failed this way may
                # still have started a session; the next attachment looks first.
                pass
            stalls = 0 if progressed else stalls + 1
            if stalls > REATTACHMENTS:
                raise SessionFailed("The AI session stopped responding.", "connection_failed")
            time.sleep(REATTACH_DELAY * stalls)
        # Usage is often recorded a few seconds after the turn ends; callers read it later when absent.
        return {"session_id": self.id, "turn_id": self.turn_id, "usage": self.usage}

    def _attach(self):
        """A stream that replays the session's events, or None when its turn has already ended."""
        if self.id is None and self.requested_at is not None:
            self.id = self._find()
            if self.id:
                self.saved(self.id, None)
        if self.id is None:
            return self._create()
        session = self.api.retrieve(self.id)
        if session.status == "failed":
            raise SessionFailed(session.error or "The AI session failed.")
        turn = self._root_turn() if self.turn_id is None or session.status == "idle" else None
        if turn is not None:
            self._note_turn(turn.id)
            if session.status == "idle" and turn.status in ("completed", "failed", "cancelled"):
                self._end(turn.status, turn.error, turn.usage)
                return None
        events = self.api.events.stream(self.id)
        if session.status == "requires_action":
            self._respond(session.required_actions)
        return events

    def _create(self):
        self.requested_at = self.requesting()
        agent = {"model": self.spec.model, "instructions": self.spec.instructions, "tools": self.spec.tools,
                 **({"reasoning": self.spec.reasoning} if self.spec.reasoning else {})}
        return self.api.create(agent=agent, environment={"type": "none"}, metadata=self.spec.metadata,
                               input=[{"role": "user", "content": self.spec.content}], stream=True)

    def _find(self):
        """The session an earlier creation started, by its metadata; sessions are listed newest first."""
        floor = self.requested_at - CLOCK_SKEW
        for scanned, session in enumerate(self.api.list(order="desc", limit=100)):
            if session.created_at < floor or scanned >= SEARCH_LIMIT:
                return None
            if all(session.metadata.get(key) == value for key, value in self.spec.metadata.items()):
                return session.id
        return None

    def _root_turn(self):
        turns = [turn for turn in self.api.turns.list(self.id) if turn.subagent_id is None]
        return max(turns, key=lambda turn: turn.created_at, default=None)

    def _follow(self, events):
        """Consume events until the session settles after its turn; True if anything new arrived."""
        progressed = False
        with events:
            try:
                for event in events:
                    if event.event_id in self.seen:
                        continue  # A re-attached stream replays what was already handled.
                    self.seen.add(event.event_id)
                    progressed = True
                    self._observe(event)
                    if self.finished:
                        break
                    self._check()
            except (RateLimitError, InternalServerError):
                pass  # Answers are stored before they are sent; pending calls are answered again.
            except APIStatusError:
                raise
            except APIError:
                # A dropped stream, or an error event the SDK raises in place of
                # yielding it. The turn may continue; the next attachment reads
                # the session's own state.
                pass
        return progressed

    def _observe(self, event):
        kind = event.type
        if self.id is None:
            self.id = getattr(event, "session_id", None) or event.session.id
            self.saved(self.id, None)
        if kind == "agent.session.turn.created" and event.turn.subagent_id is None:
            self._note_turn(event.turn_id)
        elif kind == "agent.session.requires_action":
            # A replayed event lists calls that may since have been answered, and the
            # provider accepts a repeated answer silently: answer only what is pending now.
            self._respond(self.api.retrieve(self.id).required_actions)
        elif kind in ("agent.session.turn.completed", "agent.session.turn.failed", "agent.session.turn.cancelled") \
                and event.turn.subagent_id is None:
            self._note_turn(event.turn_id)
            self._end(event.turn.status, event.turn.error, event.usage or event.turn.usage)
        elif kind == "agent.session.failed":
            raise SessionFailed(event.session.error or "The AI session failed.")
        elif kind == "agent.session.idle" and self.ended:
            self.finished = True

    def _end(self, status, error, usage):
        if status != "completed":
            raise SessionFailed(error.message if error else f"The AI turn was {status}.", error.code if error else None)
        self.ended, self.usage = True, _usage(usage)

    def _note_turn(self, turn_id):
        if turn_id != self.turn_id:
            self.turn_id = turn_id
            self.saved(self.id, turn_id)

    def _respond(self, actions):
        for action in actions:
            if action.type != "function_call" or action.call_id in self.answered:
                continue
            success, text = self.answer(action)
            result = {"type": "agent.session.input.tool_result", "call_id": action.call_id,
                      "turn_id": action.turn_id, "success": success, ("output" if success else "error"): text}
            for delay in (0.2, 0.5, 1.0, None):
                try:
                    self.api.events.create(self.id, events=[result],
                                           idempotency_key=f"minkops-tool-{self.id}-{action.call_id}")
                    break
                except BadRequestError as error:
                    body = error.body if isinstance(error.body, dict) else {}
                    if body.get("message") != f"Unknown pending tool call: {action.call_id}":
                        raise
                    # Not registered yet, or answered meanwhile: retry only while it is pending.
                    pending = {a.call_id for a in self.api.retrieve(self.id).required_actions
                               if a.type == "function_call"}
                    if action.call_id not in pending:
                        break
                    if delay is None:
                        raise
                    time.sleep(delay)
            self.answered.add(action.call_id)

    def _check(self):
        if not self.alive():
            if self.id is not None:
                with suppress(APIError):
                    cancel_turn(self.id, self.turn_id, client=self.client)
            raise SessionAbandoned("Stopped before the AI session finished.")


def turn_usage(session_id, turn_id, *, client=None):
    """A finished turn's token usage once the provider has recorded it, else None."""
    client = client or OpenAI(timeout=30, max_retries=0)
    with suppress(NotFoundError):
        return _usage(client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id).usage)
    return None


def _usage(value):
    return value.model_dump() if value is not None else None
