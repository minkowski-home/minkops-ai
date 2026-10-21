"""Thin OpenAI-hosted session adapter; no workflow-specific reasoning loop."""

import base64
import hashlib
import json
import time
from contextlib import suppress
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

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

RESULT_PATH = "/workspace/outputs/result.json"
# Long turns outlive individual provider streams; re-reading a turn is free.
STREAM_REATTACHMENTS = 3
REATTACH_DELAY = 2


def workspace_inputs(files, context, root="/workspace"):
    """Bind execution paths without changing any uploaded business evidence."""
    paths = {f"/workspace/inputs/{f['id']}{Path(f['path']).suffix.lower()}":
             f"{root}/inputs/{f['id']}{Path(f['path']).suffix.lower()}" for f in files}
    hashes = {}

    def bind(value):
        if isinstance(value, list):
            return [bind(item) for item in value]
        if isinstance(value, dict):
            result = {key: paths.get(item, item) if key in ("path", "master_lookup_path")
                      and isinstance(item, str) else bind(item) for key, item in value.items()}
            if isinstance(value.get("path"), str) and value["path"] in hashes and "sha256" in value:
                result["sha256"] = hashes[value["path"]]
            return result
        return value

    uploaded = []
    for file in files:
        original = f"/workspace/inputs/{file['id']}{Path(file['path']).suffix.lower()}"
        content = bytes(file["content"])
        if root != "/workspace" and file.get("workspace_references"):
            content = json.dumps(bind(json.loads(content)), sort_keys=True, ensure_ascii=False).encode()
            hashes[original] = hashlib.sha256(content).hexdigest()
        uploaded.append({"type": "inline", "path": paths[original],
                         "data": base64.b64encode(content).decode()})
    return uploaded, bind(context)


def skill_configuration(name, description, files):
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        for path, content in files.items():
            archive.writestr(f"{name}/{path}", content)
    return [{"type": "inline", "name": name, "description": description,
             "source": {"type": "base64", "media_type": "application/zip",
                        "data": base64.b64encode(archive_bytes.getvalue()).decode()}}]


def reconcile_turn(session_id, *, client=None):
    """Recover a persisted session's single turn without sending new input."""
    turns = list(
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.turns.list(session_id)
    )
    if len(turns) != 1:
        raise ValueError("Saved session requires turn reconciliation.")
    return turns[0].id


def close_session(session_id, *, client=None):
    """Detach this conversation after its result is durably stored."""
    # An earlier cleanup may have succeeded before its receipt was saved.
    with suppress(NotFoundError):
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.delete(session_id)


def cancel_turn(session_id, turn_id=None, *, client=None):
    """Cancel execution while preserving work; closing an SSE observer is insufficient."""
    client = client or OpenAI(timeout=15, max_retries=0)
    with suppress(NotFoundError):
        if turn_id and client.beta.agents.sessions.turns.retrieve(turn_id,session_id=session_id).status in ('completed','failed','cancelled'):
            return
        client.beta.agents.sessions.events.create(session_id,events=[{'type':'agent.session.input.cancel'}])


def execute(
    key,
    files,
    context,
    on_event,
    *,
    instructions,
    execution_instructions,
    model,
    packages,
    skill_files=None,
    skill_description=None,
    skill_name=None,
    result_path=RESULT_PATH,
    client=None,
    session_id=None,
    turn_id=None,
    environment_lease=None,
    workspace=None,
):
    """Persist IDs as events arrive and recover saved artifacts after a restart.

    The worker reconnects to a saved session rather than submitting the task twice.
    Results are accepted only from the completed turn's exact artifact path.
    """
    client = client or OpenAI(timeout=60, max_retries=0)
    workspace = workspace or context.get("config", {}).get("hosted_workspace")
    if workspace:
        result_path = workspace["result_path"]
    if session_id:
        turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
        if turn.status in ("failed", "cancelled"):
            raise ValueError(f"Agent turn {turn.status}.")
        if turn.status == "completed":
            return read_result(client, session_id, turn_id, result_path=result_path)
        events = client.beta.agents.sessions.events.stream(session_id)
    else:
        root = environment_lease.workspace["root"] if environment_lease else "/workspace"
        uploaded, bound_context = workspace_inputs(files, context, root)
        uploaded.append(
            {
                "type": "inline",
                "path": root + "/context.json",
                "data": base64.b64encode(json.dumps(bound_context).encode()).decode(),
            }
        )
        sizes = [len(base64.b64decode(f["data"])) for f in uploaded]
        if max(sizes) > 5 * 1024 * 1024 or sum(sizes) > 10 * 1024 * 1024:
            raise ValueError(
                "Selected files and catalog context exceed hosted upload limits. Select a smaller scope."
            )
        skill_name = skill_name or key
        skill_description = skill_description or instructions.split("description: ", 1)[1].splitlines()[0]
        skill_files = skill_files or {"SKILL.md": instructions}
        environment = {"type": "openai_hosted", "network": {"access": "disabled"},
                       "packages": {"python": packages}, "files": uploaded,
                       "skills": skill_configuration(skill_name, skill_description, skill_files)}
        if environment_lease:
            result_path = environment_lease.workspace["result_path"]

            def bind_instructions(text):
                return text.replace("/workspace/outputs/", "/workspace/outputs/" + root.rsplit("/", 1)[-1] + "/").replace(
                    "/workspace/context.json", root + "/context.json").replace("/workspace/inputs/", root + "/inputs/")

            instructions, execution_instructions = map(bind_instructions, (instructions, execution_instructions))
            skill_root = f"{root}/skills/{skill_name}"
            # Native skill routing is stable; the full pinned procedure/resources
            # are fresh per run, including any scripts with absolute input paths.
            routing = f"---\nname: {skill_name}\ndescription: {json.dumps(skill_description)}\n---\n" + (
                "Follow the complete pinned workflow skill at the path specified in this session's input. "
                "Use that run's resources and context exclusively; do not use previous runs' files.\n")
            environment_id = environment_lease.prepare(client, {
                "type": "openai_hosted", "network": {"access": "disabled"},
                "packages": {"python": packages},
                "skills": skill_configuration(skill_name, skill_description, {"SKILL.md": routing}),
            })
            for path, content in skill_files.items():
                uploaded.append({"type": "inline", "path": f"{skill_root}/{path}",
                                 "data": base64.b64encode(bind_instructions(content).encode()).decode()})
            for file in uploaded:
                client.beta.agents.environments.files.create(environment_id, **file)
            environment_lease.check_start()
            environment = {"type": "openai_hosted", "environment_id": environment_id}
            execution_instructions += f"\nWorkflow resources and working directory: {skill_root}."
        events = client.beta.agents.sessions.create(
            agent={"model": model, "instructions": instructions + "\n" + execution_instructions},
            environment=environment,
            input=f"Perform the workflow using {root}/context.json and the supplied files. "
            + (f"Read {skill_root}/SKILL.md and its supporting resources first. " if environment_lease else "")
            + f"Publish the required JSON at {result_path}. "
            "Read your saved JSON back and verify it before completing.",
            stream=True,
        )
    completed = False
    for attempt in range(STREAM_REATTACHMENTS + 1):
        try:
            with events:
                for event in events:
                    data = event.model_dump(mode="json")
                    session_id = data.get("session_id", session_id)
                    turn_id = data.get("turn_id", turn_id)
                    on_event(event.type, session_id, turn_id)
                    if event.type in (
                        "agent.session.turn.failed",
                        "agent.session.turn.cancelled",
                        "agent.session.environment.failed",
                    ):
                        raise ValueError(
                            "The hosted workflow could not complete. Review the run and retry explicitly."
                        )
                    if event.type == "agent.session.turn.completed":
                        completed = True
                        break
            break
        except APIError:
            # The SDK raises transport and timeout failures as APIError subclasses.
            # A dropped stream does not end the turn. Once the turn exists its
            # events can be re-read, so no session or input is ever resubmitted.
            # Before then, creation is ambiguous and stays an explicit retry.
            if not (session_id and turn_id) or attempt == STREAM_REATTACHMENTS:
                raise
            time.sleep(REATTACH_DELAY * (attempt + 1))
            turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
            if turn.status in ("failed", "cancelled"):
                raise ValueError(f"Agent turn {turn.status}.") from None
            if turn.status == "completed":
                completed = True
                break
            events = client.beta.agents.sessions.events.stream(session_id)
    if not completed:
        turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
        if turn.status != "completed":
            raise ValueError(
                "Agent stream ended before completion; the saved session can be reconciled."
            )
    return read_result(client, session_id, turn_id, result_path=result_path)


def read_result(client, session_id, turn_id, *, result_path=RESULT_PATH):
    for artifact in client.beta.agents.sessions.artifacts.list(session_id):
        if artifact.turn_id == turn_id and artifact.path == result_path:
            content = client.beta.agents.sessions.artifacts.content(
                artifact.id, session_id=session_id
            ).content
            if len(content) > 5_000_000:
                raise ValueError("Workflow result exceeds the supported size.")
            return json.loads(content)
    raise ValueError("The completed turn did not publish the required result.json artifact.")


# --- Tool sessions ---------------------------------------------------------------
# Bills and statement chunks run without an execution environment: the model
# reads the content it is given and works only through function tools. The
# worker answers exactly the calls a session lists as pending at that moment:
# never one the provider has not registered, and never one already answered,
# because the provider accepts a repeated answer silently. A dropped stream is
# re-attached. A conversation-only session must be created together with its
# input and creation is not idempotent, so a creation whose response was lost
# is found again by its metadata instead of being started twice.

# Seconds a stream may stay silent before it is re-attached.
TOOL_TIMEOUT = 120
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
