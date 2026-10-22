"""Worker lanes: leased run items, each followed through its own AI session.

A lane is a thread that claims one run item at a time, asks the run's
workflow handler what session the item needs, follows that session to its end
(runtime.openai_hosted), answers its tool calls, and settles the item. Lanes
share a small connection pool and hold a connection only while they record
state or answer a call, never while the model works, so many lanes fit in
little memory.

One heartbeat renews every lease the host holds and tells a lane when its
fence is gone (another worker reclaimed the item) or its task was stopped. A
LISTEN connection wakes idle lanes as soon as an item is queued; a slow poll
covers a lost notification. When the host leaves, it expires its leases
rather than releasing its items, so a successor reattaches to the same paid
session instead of starting another.

A handler (work.HANDLER_MODULES) provides:

- `session(connection, run, item)`: the Session to run for the item, None
  when the item finished without one, or raise Wait to park it on a blocker.
  It runs again when an item is resumed, so anything it records must be
  idempotent;
- `settle(connection, run, item, outcome)`: in the transaction that finishes
  the item, settle its records from what the session proposed or why it failed.
  It may raise Wait to park the item until a blocker is released, and it runs
  again when the item resumes;
- optionally `describe(state, items, records)`, the task summary for work.refresh.
"""

import logging
import threading
import time
from dataclasses import dataclass

import psycopg
from openai import APIError, APIStatusError, OpenAI
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import work
from .runtime import tools
from .runtime.openai_hosted import (
    TOOL_TIMEOUT,
    SessionAbandoned,
    SessionFailed,
    SessionSpec,
    close_session,
    run_tool_session,
    session_usage,
)

log = logging.getLogger(__name__)
# Lanes per worker by default; slice 12 measures how far this can go.
LANES = 12
HEARTBEAT_SECONDS = 60
POLL_SECONDS = 30
# Finished sessions are closed on this cadence; usage not reported within USAGE_WAIT stays unknown.
CLOSE_SECONDS = 10
USAGE_WAIT = 60
# How long a drain waits for its finished sessions to be closed before leaving them to a successor.
CLOSE_GRACE = 3 * USAGE_WAIT
POOL_SIZE = 4
# Attempts per item, and the wait before each retry, for failures worth retrying.
ATTEMPTS = 3
RETRY_DELAYS = (30, 120)
CHANNEL = "minkops_work"


@dataclass(frozen=True)
class Session:
    """What a handler asks a lane to run for one item."""

    model: str
    instructions: str
    content: list
    tools: dict
    # The handler's own context for its tools, rebuilt whenever an item is resumed.
    state: object = None
    reasoning: dict | None = None
    # The session's work as its constrained final answer, checked once per turn; None for a session that
    # proposes through its tools.
    answer: tools.Answer | None = None
    service_tier: str | None = None


@dataclass(frozen=True)
class Call:
    """What a tool handler works with: this call's transaction, its run and item."""

    connection: object
    run: dict
    item: dict
    state: object


@dataclass(frozen=True)
class Outcome:
    usage: dict | None = None
    # None when the session completed; otherwise a short reason a person can act on.
    error: str | None = None
    stopped: bool = False


class Wait(Exception):
    """Raised by a handler to park an item until a named blocker is released."""

    def __init__(self, blocker):
        super().__init__(blocker)
        self.blocker = blocker


class Superseded(Exception):
    """This lane no longer owns its item: the lease was reclaimed, or the host is leaving."""


class _Lease:
    """One claim of an item: its fence, the heartbeat's verdict, and the session it has reached."""

    def __init__(self, item):
        self.id, self.token, self.session_id = item["id"], item["lease_token"], item["session_id"]
        self.lost = self.stopped = False


class Host:
    """The lanes of one worker process, optionally serving one tenant. Use as a context manager."""

    def __init__(self, url, *, lanes, client=None, resolve=work.handler_for, tenant_id=None, pool_size=POOL_SIZE,
                 lease_seconds=work.LEASE_SECONDS, heartbeat_seconds=HEARTBEAT_SECONDS, poll_seconds=POLL_SECONDS,
                 close_seconds=CLOSE_SECONDS):
        if type(lanes) is not int or not 1 <= lanes <= 16:
            raise ValueError("Lanes must be between 1 and 16.")
        self.url, self.size, self.resolve, self.tenant_id = url, lanes, resolve, tenant_id
        self.lease_seconds, self.heartbeat_seconds, self.poll_seconds = lease_seconds, heartbeat_seconds, poll_seconds
        self.close_seconds = close_seconds
        self.client = client or OpenAI(timeout=TOOL_TIMEOUT, max_retries=0)
        self.pool = ConnectionPool(url, min_size=1, max_size=pool_size, open=False, name="lanes",
                                   kwargs={"row_factory": dict_row, "options": "-c statement_timeout=30000"})
        self.leases, self.busy, self.claiming, self.leaving = {}, 0, True, False
        self.wakes = 0
        self.changed = threading.Condition()
        self.threads = []

    def __enter__(self):
        self.pool.open(wait=True, timeout=30)
        targets = [self._heartbeat, self._listen, self._closer] + [self._lane] * self.size
        self.threads = [threading.Thread(target=target, name=f"lane-{n}", daemon=True)
                        for n, target in enumerate(targets)]
        for thread in self.threads:
            thread.start()
        return self

    def __exit__(self, *exc):
        self.leave()
        deadline = time.monotonic() + 5
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        self.pool.close()

    # --- control ------------------------------------------------------------

    def wake(self):
        with self.changed:
            self.wakes += 1
            self.changed.notify_all()

    def stop_claiming(self):
        """Finish the items in hand and take no more, for a drain that has reached its deadline."""
        self.claiming = False
        self.wake()

    def leave(self):
        """Stop at once and hand every item still held to a successor, sessions included."""
        self.claiming, self.leaving = False, True
        held = [(lease.id, lease.token) for lease in self._held()]
        if held:
            try:
                with self.pool.connection() as connection:
                    work.hand_off(connection, held)
            except psycopg.Error as error:
                log.warning("Leases expire on their own (%s)", type(error).__name__)
        self.wake()

    def settled(self, connection):
        """True when no lane is busy, nothing is runnable and finished sessions are closed: a drain may end.

        A session that finished long ago and still could not be deleted does
        not hold a drain open; the provider expires it on its own.
        """
        with self.changed:
            if self.busy:
                return False
        if work.runnable(connection, tenant_id=self.tenant_id):
            self.wake()
            return False
        return not work.unclosed(connection, tenant_id=self.tenant_id, limit=1, within=CLOSE_GRACE)

    def _held(self):
        with self.changed:
            return list(self.leases.values())

    def wait_idle(self, timeout):
        """Block until no lane is busy, or the timeout passes."""
        deadline = time.monotonic() + timeout
        with self.changed:
            while self.busy and time.monotonic() < deadline:
                self.changed.wait(deadline - time.monotonic())
            return not self.busy

    # --- threads ------------------------------------------------------------

    def _lane(self):
        while not self.leaving:
            with self.changed:
                seen = self.wakes
            claimed = self._claim() if self.claiming else None
            if claimed is None:
                with self.changed:
                    if self.wakes == seen and not self.leaving:
                        self.changed.wait(self.poll_seconds)
                continue
            item, lease = claimed
            try:
                self._work(item, lease)
            except Superseded:
                pass
            except psycopg.OperationalError as error:
                # The database is unreachable: the lease lapses and a lane resumes the item.
                log.warning("Item %s left for a successor (%s)", item["id"], type(error).__name__)
            except Exception:
                log.exception("Item %s failed in the worker", item["id"])
                self._give_up(item, lease)
            finally:
                with self.changed:
                    self.leases.pop(lease.token, None)
                    self.busy -= 1
                    self.changed.notify_all()

    def _give_up(self, item, lease):
        try:
            self._finish(item, lease, "failed", Outcome(error="The worker could not process this input."),
                         error_code="worker_error")
        except Exception:  # noqa: BLE001 - the lease lapses and a lane resumes the item
            log.exception("Item %s is left for a successor", item["id"])

    def _claim(self):
        try:
            with self.pool.connection() as connection:
                item = work.claim(connection, tenant_id=self.tenant_id, lease_seconds=self.lease_seconds)
                if item is None:
                    return None
                lease = _Lease(item)
                with self.changed:
                    self.busy += 1
                    # Keyed by token: a retried item can be claimed again before this lane lets go.
                    self.leases[lease.token] = lease
                return item, lease
        except psycopg.Error as error:
            log.warning("Claim will retry (%s)", type(error).__name__)
            return None

    def _heartbeat(self):
        while self._pause(self.heartbeat_seconds):
            self.beat()

    def _closer(self):
        while self._pause(self.close_seconds):
            self.close_finished()

    def _pause(self, seconds):
        """Wait out one period; False once the host is leaving."""
        with self.changed:
            self.changed.wait_for(lambda: self.leaving, timeout=seconds)
            return not self.leaving

    def beat(self):
        """Renew every lease held; flag lanes whose fence is gone or whose task was stopped."""
        leases = self._held()
        try:
            with self.pool.connection() as connection:
                renewed = work.renew_all(connection, [(lease.id, lease.token) for lease in leases], self.lease_seconds)
        except psycopg.Error as error:
            log.warning("Lease renewal will retry (%s)", type(error).__name__)
            return
        for lease in leases:
            lease.lost = lease.id not in renewed
            lease.stopped = renewed.get(lease.id) == "stopped"

    def close_finished(self):
        """Record finished sessions' usage as the provider reports it, then delete them there."""
        try:
            with self.pool.connection() as connection:
                rows = work.unclosed(connection, tenant_id=self.tenant_id)
        except psycopg.Error as error:
            log.warning("Session cleanup will retry (%s)", type(error).__name__)
            return
        for row in rows:
            try:
                usage = row["usage"]
                if usage is None and row["turn_id"]:
                    usage = session_usage(row["session_id"], client=self.client)
                    if usage is None and row["age"] < USAGE_WAIT:
                        continue
                close_session(row["session_id"], client=self.client)
                with self.pool.connection() as connection:
                    work.closed(connection, row["id"], row["session_id"], usage)
            except (APIError, psycopg.Error) as error:
                log.warning("Session %s stays open for now (%s)", row["session_id"], type(error).__name__)

    def _listen(self):
        while not self.leaving:
            try:
                with psycopg.connect(self.url, autocommit=True) as connection:
                    connection.execute(f"LISTEN {CHANNEL}")
                    self.wake()  # anything queued while not listening
                    while not self.leaving:
                        for _ in connection.notifies(timeout=1.0):
                            self.wake()
            except psycopg.Error as error:
                log.warning("Work notifications will reconnect (%s)", type(error).__name__)
                time.sleep(5)

    # --- one item -----------------------------------------------------------

    def _work(self, item, lease):
        with self.pool.connection() as connection:
            run = work.get_run(connection, item["tenant_id"], item["run_id"])
            handler = self.resolve(run)
            try:
                session = handler.session(connection, run, item)
            except Wait as parked:
                if not work.wait(connection, item["id"], lease.token, parked.blocker):
                    raise Superseded() from None
                return
            # The task moves on from 'getting ready' as soon as reading starts, not when the first session ends.
            work.refresh(connection, item["tenant_id"], item["run_id"], describe=getattr(handler, "describe", None))
        if session is None:
            self._finish(item, lease, "done", Outcome(), run, handler)
            return
        try:
            result = self._follow(item, lease, run, session)
        except SessionAbandoned:
            self._finish(item, lease, "cancelled", Outcome(error="Stopped before this input was read.", stopped=True),
                         run, handler)
        except SessionFailed as failure:
            self._failed(item, lease, run, handler, failure.code, str(failure), failure.transient)
        except APIStatusError as refusal:
            # The provider refused the request itself; repeating it would be refused again.
            message = refusal.body.get("message") if isinstance(refusal.body, dict) else None
            self._failed(item, lease, run, handler, f"provider_{refusal.status_code}",
                         f"The AI service refused this input: {message or refusal.message}", False)
        else:
            self._finish(item, lease, "done", Outcome(usage=result["usage"]), run, handler)

    def _follow(self, item, lease, run, session):
        """Run the item's session, every provider ID and answer recorded under the item's lease."""

        def alive():
            if lease.lost or self.leaving:
                raise Superseded()
            return not lease.stopped

        def answer(call):
            alive()  # a lane that is leaving or lost its fence must not renew the lease by answering
            return self._fenced(lambda connection: work.renew(connection, item["id"], lease.token, self.lease_seconds)
                                and tools.answer(connection, item, lease.session_id, call, session.tools,
                                                 Call(connection, run, item, session.state)))

        def saved(session_id, turn_id):
            alive()
            lease.session_id = session_id
            self._fenced(lambda connection: work.save_session(connection, item["id"], lease.token, session_id,
                                                              turn_id))

        def final(turn_id, text):
            alive()
            verdict = self._fenced(lambda connection: work.renew(connection, item["id"], lease.token, self.lease_seconds)
                                   and {"correction": tools.conclude(connection, item, lease.session_id, turn_id, text,
                                                                     session.answer,
                                                                     Call(connection, run, item, session.state))})
            return verdict["correction"]

        spec = SessionSpec(model=session.model, instructions=session.instructions, content=session.content,
                           tools=[tool.function() for tool in session.tools.values()], reasoning=session.reasoning,
                           answer_schema=session.answer.tool.input_schema if session.answer else None,
                           service_tier=session.service_tier,
                           metadata={"minkops_item": str(item["id"]), "minkops_attempt": str(item["attempt"]),
                                     "minkops_run": str(item["run_id"]), "minkops_tenant": str(item["tenant_id"])})
        requested = item["session_requested_at"]
        return run_tool_session(
            spec, answer=answer, saved=saved, alive=alive, final=final if session.answer else None,
            client=self.client, session_id=item["session_id"],
            requesting=lambda: self._fenced(lambda c: work.request_session(c, item["id"], lease.token)),
            requested_at=requested.timestamp() if requested else None)

    def _fenced(self, statement):
        """Run a statement in its own transaction; a falsy result means the fence is gone."""
        with self.pool.connection() as connection:
            result = statement(connection)
            if result in (None, False):
                connection.rollback()
                raise Superseded()
            return result

    def _failed(self, item, lease, run, handler, code, message, transient):
        if transient and item["attempt"] < ATTEMPTS:
            delay = RETRY_DELAYS[min(item["attempt"], len(RETRY_DELAYS)) - 1]
            # The retry starts a new session; the closer records this one's usage, then deletes it.
            self._fenced(lambda connection: work.retry(connection, item["id"], lease.token, delay=delay,
                                                       error_code=code, error=message))
            return
        self._finish(item, lease, "failed", Outcome(error=message), run, handler, error_code=code)

    def _finish(self, item, lease, state, outcome, run=None, handler=None, *, error_code=None):
        """Settle the item's records and finish it in one fenced transaction; the closer ends its session.

        A handler that still needs something before the item is complete (a
        member's answer) raises Wait from settle, and the item parks instead.
        """
        with self.pool.connection() as connection:
            run = run or work.get_run(connection, item["tenant_id"], item["run_id"])
            handler = handler or self.resolve(run)
            try:
                handler.settle(connection, run, item, outcome)
                fenced = work.finish(connection, item["id"], lease.token, state, error_code=error_code,
                                     error=outcome.error, usage=outcome.usage)
            except Wait as parked:
                fenced = work.wait(connection, item["id"], lease.token, parked.blocker)
            if not fenced:
                connection.rollback()
                raise Superseded()
            work.refresh(connection, item["tenant_id"], item["run_id"], describe=getattr(handler, "describe", None))
