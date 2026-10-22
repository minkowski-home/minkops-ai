"""Worker lanes on PostgreSQL, against the fake Agents API.

Each test drives real leases, wake-ups and fenced writes: parallel sessions,
a blocker released by a commit, a successor resuming a session its
predecessor left, a reclaimed fence, a stopped task, and retries.
"""

import os
import time

import psycopg
import pytest
from fake_agents import USAGE, FakeAgents, Script

from minkops_platform import lanes, work
from minkops_platform.runtime import openai_hosted
from minkops_platform.runtime.tools import Tool, ToolError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
SUBJECTS = {"type": "object", "properties": {"subjects": {"type": "array", "items": {"type": "string"}}},
            "required": ["subjects"], "additionalProperties": False}
AMOUNT = {"type": "object", "properties": {"amount": {"type": "string"}}, "required": ["amount"],
          "additionalProperties": False}
LOOKUP = [("find_ledger", {"subjects": ["Acme Steel"]})]
PROPOSE = [("propose", {"amount": "1180.00"})]
BLOCKER = {"kind": "sync", "ref": "pc-1"}


def find_ledger(call, arguments):
    return {"ledgers": [{"name": name, "group": "Sundry Creditors"} for name in arguments["subjects"]]}


def propose(call, arguments):
    """Record the proposal once per item; a resumed session updates the same record."""
    if arguments["amount"] == "0":
        raise ToolError("The amount must be the bill total.")
    existing = call.connection.execute("SELECT * FROM run_records WHERE item_id=%s", (call.item["id"],)).fetchone()
    if existing:
        work.update_record(call.connection, existing, proposal=arguments)
    else:
        work.add_records(call.connection, call.item, [{"kind": "bill", "source": call.item["source"],
                                                       "proposal": arguments, "status": "proposed"}])
    return {"accepted": True}


TOOLS = {"find_ledger": Tool("find_ledger", "Find ledgers.", SUBJECTS, find_ledger),
         "propose": Tool("propose", "Propose the entry.", AMOUNT, propose)}


class Desk:
    """A test workflow: one session per bill; items with `park` wait for a sync first."""

    def __init__(self):
        self.settled = {}

    def session(self, connection, run, item):
        if item["source"].get("park") and not item["source"].get("released"):
            connection.execute("UPDATE run_items SET source=source || '{\"released\": true}' WHERE id=%s",
                               (item["id"],))
            raise lanes.Wait(BLOCKER)
        return lanes.Session(model="gpt-6-luna", instructions="Enter the bill.", tools=TOOLS,
                             content=[{"type": "input_text", "text": item["source"]["file_id"]}])

    def settle(self, connection, run, item, outcome):
        self.settled[item["source"]["file_id"]] = outcome


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(openai_hosted.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(lanes, "RETRY_DELAYS", (0, 0))


@pytest.fixture
def desk():
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        operator = factory.user(db, tenant, role="admin")
        scope = {"db": db, "tenant": tenant, "operator": operator, "client": factory.client(db, tenant),
                 "workflow": factory.workflow(db, tenant), "handler": Desk()}
        db.commit()
        yield scope


def launch(desk, *sources):
    import factory
    run = factory.run(desk["db"], desk["tenant"], desk["client"], desk["workflow"], desk["operator"],
                      [work.ItemSpec("bill", source) for source in sources])
    desk["db"].commit()
    return run


def host(desk, fake, **options):
    options = {"lanes": 2, "heartbeat_seconds": 0.2, "poll_seconds": 0.5, "close_seconds": 0.1, **options}
    return lanes.Host(os.environ["TEST_DATABASE_URL"], client=fake, resolve=lambda run: desk["handler"],
                      tenant_id=desk["tenant"]["id"], **options)


def items(desk, run):
    desk["db"].commit()  # a fresh snapshot
    return desk["db"].execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()


def sessions(desk, run):
    """Every provider session the run's items opened, in item order and then as opened."""
    desk["db"].commit()  # a fresh snapshot
    return desk["db"].execute("""SELECT s.* FROM item_sessions s JOIN run_items i ON i.id=s.item_id
                                 WHERE i.run_id=%s ORDER BY i.ordinal, s.opened_at""", (run["id"],)).fetchall()


def until(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out")


def test_items_run_in_parallel_sessions_and_settle_with_their_usage(desk):
    # Usage arrives after the turn has ended, as measured live.
    fake = FakeAgents(Script(LOOKUP, PROPOSE, usage_after=1))
    run = launch(desk, {"file_id": "a"}, {"file_id": "b"}, {"file_id": "c"})
    with host(desk, fake, lanes=3) as lanes_:
        assert not lanes_.settled(desk["db"])
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
        until(lambda: lanes_.settled(desk["db"]))
        until(lambda: len(sessions(desk, run)) == 3 and all(s["closed"] for s in sessions(desk, run)))
    assert [i["attempt"] for i in items(desk, run)] == [1] * 3
    assert [(s["attempt"], s["usage"], s["closed"]) for s in sessions(desk, run)] == [(1, USAGE, True)] * 3
    calls = desk["db"].execute("""SELECT i.ordinal, c.name, c.success FROM tool_calls c JOIN run_items i ON i.id=c.item_id
                                  WHERE i.run_id=%s ORDER BY i.ordinal, c.created_at""", (run["id"],)).fetchall()
    assert [(c["ordinal"], c["name"], c["success"]) for c in calls] == [
        (n, name, True) for n in range(3) for name in ("find_ledger", "propose")]
    records = desk["db"].execute("SELECT status, proposal FROM run_records WHERE run_id=%s", (run["id"],)).fetchall()
    assert [(r["status"], r["proposal"]) for r in records] == [("proposed", {"amount": "1180.00"})] * 3
    assert work.get_run(desk["db"], desk["tenant"]["id"], run["id"])["state"] == "review"
    # One session per item, identified for recovery, and deleted once settled.
    assert fake.store == {} and fake.streams == 3
    assert set(desk["handler"].settled) == {"a", "b", "c"}
    assert all(outcome.error is None for outcome in desk["handler"].settled.values())


def test_a_released_blocker_wakes_idle_lanes_at_once(desk):
    fake = FakeAgents(Script(PROPOSE))
    run = launch(desk, {"file_id": "a", "park": True})
    # Poll rarely: only the committed release's notification can start the item in time.
    with host(desk, fake, poll_seconds=60) as lanes_:
        until(lambda: items(desk, run)[0]["state"] == "waiting")
        until(lambda: lanes_.settled(desk["db"]))  # nothing runnable while the item waits
        assert work.release(desk["db"], desk["tenant"]["id"], BLOCKER) == 1
        desk["db"].commit()
        until(lambda: items(desk, run)[0]["state"] == "done", timeout=5)


def test_the_task_says_reading_has_begun_once_a_lane_starts_its_item(desk):
    import factory
    fake = FakeAgents(Script(PROPOSE))
    run = factory.run(desk["db"], desk["tenant"], desk["client"], desk["workflow"], desk["operator"],
                      [work.ItemSpec("bill", {"file_id": "a"}, waiting_on=BLOCKER)])
    desk["db"].commit()
    with host(desk, fake) as lanes_:
        assert work.release(desk["db"], desk["tenant"]["id"], BLOCKER) == 1
        desk["db"].commit()
        until(lambda: items(desk, run)[0]["state"] == "done")
        until(lambda: lanes_.settled(desk["db"]))
    events = desk["db"].execute("SELECT summary FROM task_events WHERE task_id=%s ORDER BY id", (run["task_id"],))
    # Not 'Getting ready.' until the session ends: the task moves on as soon as a lane starts reading.
    assert [event["summary"] for event in events][:2] == ["Getting ready.", "0 of 1 input read."]


def test_a_successor_resumes_the_session_its_predecessor_left(desk):
    first = None

    def leave_after_lookup(answers, session):
        first.leave()
        return PROPOSE

    fake = FakeAgents(Script(LOOKUP, leave_after_lookup))
    run = launch(desk, {"file_id": "a"})
    first = host(desk, fake, lanes=1)
    with first:
        until(lambda: first.leaving and not first.busy)
    [item] = items(desk, run)
    [session] = fake.sessions
    assert item["state"] == "running" and item["session_id"] == session.id and session.status == "requires_action"
    assert fake.cancels == 0  # the paid session was left for a successor, not cancelled
    with host(desk, fake, lanes=1):
        until(lambda: sessions(desk, run)[0]["closed"])
    [item] = items(desk, run)
    assert (item["state"], item["attempt"]) == ("done", 1)
    # The successor carried on the same session: one session, its usage counted once.
    assert [(s["session_id"], s["usage"]) for s in sessions(desk, run)] == [(session.id, USAGE)]
    assert len(fake.store) == 0 and fake.cancels == 0 and fake.resent == 0
    assert [(a["name"], a["success"]) for a in session.answers] == [("find_ledger", True), ("propose", True)]
    logged = desk["db"].execute("SELECT name FROM tool_calls WHERE item_id=%s ORDER BY created_at",
                                (item["id"],)).fetchall()
    assert [row["name"] for row in logged] == ["find_ledger", "propose"]


def test_a_lane_whose_item_was_reclaimed_stops_without_writing_or_cancelling(desk):
    def reclaim_elsewhere(answers, session):
        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as other:
            other.execute("UPDATE run_items SET lease_token=gen_random_uuid() WHERE run_id=%s", (run["id"],))
        return PROPOSE

    fake = FakeAgents(Script(LOOKUP, reclaim_elsewhere))
    run = launch(desk, {"file_id": "a"})
    with host(desk, fake, lanes=1) as lanes_:
        until(lambda: fake.sessions and fake.sessions[0].status == "requires_action"
              and fake.sessions[0].answers and not lanes_.busy)
    [item] = items(desk, run)
    assert item["state"] == "running" and fake.cancels == 0
    assert desk["db"].execute("SELECT count(*) AS n FROM tool_calls WHERE item_id=%s AND name='propose'",
                              (item["id"],)).fetchone()["n"] == 0
    assert desk["db"].execute("SELECT count(*) AS n FROM run_records WHERE item_id=%s",
                              (item["id"],)).fetchone()["n"] == 0


def test_stopping_the_task_cancels_its_running_session(desk):
    def stop_task(answers, session):
        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as other:
            other.execute("UPDATE tasks SET control_state='stopped' WHERE id=%s", (run["task_id"],))
        stopper.beat()
        return PROPOSE

    fake = FakeAgents(Script(LOOKUP, stop_task))
    run = launch(desk, {"file_id": "a"})
    stopper = host(desk, fake, lanes=1, heartbeat_seconds=60)
    with stopper:
        until(lambda: sessions(desk, run) and sessions(desk, run)[0]["closed"])
    assert items(desk, run)[0]["state"] == "cancelled"
    assert fake.cancels == 1 and fake.store == {}
    assert desk["handler"].settled["a"].stopped


def test_retries_start_a_new_session_and_a_refusal_fails_only_its_item(desk):
    def script_for(metadata, content):
        name = content[0]["text"]
        if name == "flaky" and metadata["minkops_attempt"] == "1":
            return Script(LOOKUP, ending="failed", error_code="server_overloaded")
        if name == "huge":
            return Script(ending="failed", error_code="context_length_exceeded")
        return Script(PROPOSE)

    fake = FakeAgents(script_for=script_for)
    run = launch(desk, {"file_id": "flaky"}, {"file_id": "huge"})
    with host(desk, fake):
        until(lambda: {i["state"] for i in items(desk, run)} == {"done", "failed"})
        until(lambda: len(sessions(desk, run)) == 3 and all(s["closed"] for s in sessions(desk, run)))
    flaky, huge = items(desk, run)
    assert (flaky["state"], flaky["attempt"], flaky["error_code"]) == ("done", 2, None)
    assert (huge["state"], huge["attempt"], huge["error_code"]) == ("failed", 1, "context_length_exceeded")
    assert desk["handler"].settled["huge"].error == "The turn failed (context_length_exceeded)."
    # Each attempt had its own session; the retried item's first session was closed, not resumed.
    attempts = sorted((s.content[0]["text"], s.metadata["minkops_attempt"]) for s in fake.created)
    assert attempts == [("flaky", "1"), ("flaky", "2"), ("huge", "1")]
    # Every session's usage counts, the retried attempt's included, so a run's spend is never under-counted.
    assert [(s["attempt"], s["usage"]) for s in sessions(desk, run)] == [(1, USAGE), (2, USAGE), (1, USAGE)]
    spent = work.usage(desk["db"], desk["tenant"]["id"], run["id"])
    assert (spent["sessions"], spent["input_tokens"], spent["cached_tokens"], spent["output_tokens"]) == (3, 2700, 1800, 120)


def test_a_drain_waits_for_a_finished_session_to_close_unless_it_finished_long_ago(desk):
    run = launch(desk, {"file_id": "a"}, {"file_id": "b"})
    fresh, stale = items(desk, run)
    for item, finished in ((fresh, "now()"), (stale, "now() - interval '1 hour'")):
        desk["db"].execute(f"""UPDATE run_items SET state='done', session_id=%s, finished_at={finished}
                               WHERE id=%s""", (f"session-{item['id']}", item["id"]))
        desk["db"].execute(f"""INSERT INTO item_sessions (tenant_id, item_id, session_id, attempt, finished_at)
                               VALUES (%s, %s, %s, 1, {finished})""",
                           (item["tenant_id"], item["id"], f"session-{item['id']}"))
    desk["db"].commit()
    # A closer that never runs here: the drain's verdict rests on the sessions' state alone.
    with host(desk, FakeAgents(), close_seconds=3600) as lanes_:
        assert not lanes_.settled(desk["db"])
        desk["db"].execute("UPDATE item_sessions SET closed=true WHERE item_id=%s", (fresh["id"],))
        desk["db"].commit()
        # A session that still could not be deleted an hour on is the provider's to expire, not a reason to stay up.
        assert lanes_.settled(desk["db"])


def test_a_drain_acknowledges_its_wake_up_only_after_the_lanes_finish(desk):
    from minkops_platform.worker_hosting import drain
    fake = FakeAgents(Script(LOOKUP, PROPOSE))
    run = launch(desk, {"file_id": "a"}, {"file_id": "b"})
    with host(desk, fake) as lanes_:
        assert drain(os.environ["TEST_DATABASE_URL"], lanes_)
        # Acknowledged only once both items finished and their sessions were closed with their usage.
        assert {i["state"] for i in items(desk, run)} == {"done"}
        assert [(s["closed"], s["usage"]) for s in sessions(desk, run)] == [(True, USAGE)] * 2
    wakeup = desk["db"].execute("SELECT generation, acknowledged, lease_until FROM worker_wakeup").fetchone()
    assert wakeup["generation"] == wakeup["acknowledged"] and wakeup["lease_until"] is None
