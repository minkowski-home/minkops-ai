"""Runs, items, records and decisions: durable scheduling with committed wake-ups.

Includes the cases the 21 October runtime review found untested: confirming
after the worker has drained, losing the response after a commit, and the same
decision sent twice.
"""

import json
import os
import select
import threading

import psycopg
import pytest

from minkops_platform import work
from minkops_platform.errors import ServiceError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")


@pytest.fixture
def scope():
    """A committed tenant, client, workflow and operator, removed rows are left for the disposable DB."""
    import factory
    with factory.connect() as connection:
        tenant = factory.tenant(connection)
        operator = factory.user(connection, tenant, role="admin")
        client = factory.client(connection, tenant)
        flow = factory.workflow(connection, tenant)
        connection.commit()
        yield {"tenant": tenant, "operator": operator, "client": client, "workflow": flow}


def launch(connection, scope, items, *, key=None):
    import factory
    return factory.run(connection, scope["tenant"], scope["client"], scope["workflow"], scope["operator"], items, key=key)


def generation(connection):
    return connection.execute("SELECT generation,acknowledged FROM worker_wakeup").fetchone()


def test_launch_pins_a_small_run_with_its_task_bundle_and_items(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"}), work.ItemSpec("bill", {"file_id": "b"})])
        task = db.execute("SELECT * FROM tasks WHERE id=%s", (run["task_id"],)).fetchone()
        assert (task["client_id"], task["status"]) == (scope["client"]["id"], "running")
        # The first summary is the run's own description, as every later one is.
        assert task["summary"] == "0 of 2 inputs read."
        items = db.execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()
        assert [(i["ordinal"], i["state"], i["source"]["file_id"]) for i in items] == [(0, "queued", "a"), (1, "queued", "b")]
        bundle = db.execute("SELECT content FROM run_bundles WHERE tenant_id=%s AND digest=%s",
                            (scope["tenant"]["id"], run["bundle_digest"])).fetchone()
        assert bundle["content"]["tools"] == ["propose"]
        # Another run with the same procedure reuses the stored bundle.
        again = launch(db, scope, [work.ItemSpec("bill", {"file_id": "c"})])
        assert again["bundle_digest"] == run["bundle_digest"]
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute("UPDATE runs SET config=%s WHERE id=%s",
                       (json.dumps({"snapshot": "x" * 20000}), run["id"]))


def test_queued_items_wake_workers_only_when_their_transaction_commits(scope):
    import factory
    with factory.connect() as listener, factory.connect() as db:
        listener.autocommit = True
        listener.execute("LISTEN minkops_work")
        before = generation(db)["generation"]
        db.commit()
        launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        assert not select.select([listener.pgconn.socket], [], [], 0.2)[0], "no notice before commit"
        db.commit()
        assert select.select([listener.pgconn.socket], [], [], 2)[0]
        assert [n.payload for n in listener.notifies(timeout=1, stop_after=1)] == ["bill"]
        assert generation(db)["generation"] > before


def test_each_item_is_claimed_by_one_lane_and_fenced_by_its_lease(scope):
    import factory
    with factory.connect() as db:
        launch(db, scope, [work.ItemSpec("bill", {"file_id": str(n)}) for n in range(3)])
        db.commit()
    claimed, errors = [], []

    def lane():
        try:
            with factory.connect() as connection:
                item = work.claim(connection, kinds=("bill",), tenant_id=scope["tenant"]["id"])
                connection.commit()
                claimed.append(item["id"] if item else None)
        except Exception as error:  # pragma: no cover - surfaced below
            errors.append(error)

    threads = [threading.Thread(target=lane) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not errors
    assert len({c for c in claimed if c}) == 3 and claimed.count(None) == 2
    with factory.connect() as db:
        item = db.execute("SELECT * FROM run_items WHERE id=%s", (next(c for c in claimed if c),)).fetchone()
        assert item["state"] == "running" and item["attempt"] == 1
        assert not work.save_session(db, item["id"], "00000000-0000-0000-0000-000000000000", "sess", "turn")
        assert work.save_session(db, item["id"], item["lease_token"], "sess", "turn")
        assert work.finish(db, item["id"], item["lease_token"], "done")
        assert not work.finish(db, item["id"], item["lease_token"], "failed", error_code="late")


def test_an_expired_lease_resumes_its_attempt_and_a_recheck_starts_a_new_one(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        item = work.claim(db, kinds=("bill",), tenant_id=scope["tenant"]["id"])
        work.save_session(db, item["id"], item["lease_token"], "sess-1", "turn-1")
        db.execute("UPDATE run_items SET lease_until=now()-interval '1 second' WHERE id=%s", (item["id"],))
        again = work.claim(db, kinds=("bill",), tenant_id=scope["tenant"]["id"])
        assert again["id"] == item["id"] and again["reclaimed"]
        assert (again["session_id"], again["turn_id"], again["attempt"]) == ("sess-1", "turn-1", 1)
        assert again["started_at"] == item["started_at"]
        assert again["lease_token"] != item["lease_token"]
        assert not work.renew(db, item["id"], item["lease_token"])  # The old lane has lost its fence.
        assert run["id"] == again["run_id"]
        # A recheck is a new attempt: a fresh session, timed from its own start (an hour after the first here).
        assert work.finish(db, item["id"], again["lease_token"], "done")
        first = db.execute("UPDATE run_items SET started_at=started_at-interval '1 hour' WHERE id=%s RETURNING *",
                           (item["id"],)).fetchone()
        work.requeue_item(db, scope["tenant"]["id"], item["id"])
        fresh = work.claim(db, kinds=("bill",), tenant_id=scope["tenant"]["id"])
        assert (fresh["session_id"], fresh["attempt"]) == (None, 2)
        assert fresh["started_at"] > first["started_at"]


def test_paused_and_stopped_tasks_are_never_claimed(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        db.execute("UPDATE tasks SET control_state='paused' WHERE id=%s", (run["task_id"],))
        assert work.claim(db, kinds=("bill",), tenant_id=scope["tenant"]["id"]) is None


def test_confirming_after_the_worker_drained_releases_waiting_items_with_a_wake_up(scope):
    """The 21 October P0: a released dependency must not wait for the hourly sweep."""
    import factory

    from minkops_platform.worker_hosting import dispatch
    with factory.connect() as db:
        blocker = {"kind": "question", "ref": "q-1"}
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"}, waiting_on=blocker),
                                 work.ItemSpec("bill", {"file_id": "b"}, waiting_on={"kind": "question", "ref": "q-2"})])
        db.commit()
        # The worker drained: it acknowledged everything it observed and released its lease.
        db.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL,dispatch_token=NULL")
        db.commit()
        assert work.release(db, scope["tenant"]["id"], blocker) == 1
        db.commit()
        states = {r["file_id"]: r["state"] for r in db.execute(
            "SELECT source->>'file_id' AS file_id,state FROM run_items WHERE run_id=%s", (run["id"],)).fetchall()}
        assert states == {"a": "queued", "b": "waiting"}
    submissions = []
    assert dispatch(os.environ["TEST_DATABASE_URL"], lambda: submissions.append(True))
    assert submissions == [True]


def record(db, scope, run):
    item = db.execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal LIMIT 1", (run["id"],)).fetchone()
    (row,) = work.add_records(db, item, [{"kind": "bill", "source": {"file_id": "a"}, "status": "held",
                                          "hold_codes": ["supplier_missing"]}])
    return row


def test_the_same_decision_sent_twice_returns_one_receipt_and_applies_once(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        row = record(db, scope, run)
        applied = []

        def apply(current):
            applied.append(current["version"])
            work.update_record(db, current, status="deferred")
            return {"status": "deferred"}

        first = work.decide(db, tenant_id=scope["tenant"]["id"], record_id=row["id"], version=row["version"],
                            actor_id=scope["operator"]["id"], action="nothing", apply=apply)
        db.commit()
        # The response was lost after commit; the client retries the same decision.
        second = work.decide(db, tenant_id=scope["tenant"]["id"], record_id=row["id"], version=row["version"],
                             actor_id=scope["operator"]["id"], action="nothing", apply=apply)
        assert applied == [1]
        assert (first["replayed"], second["replayed"]) == (False, True)
        assert {k: v for k, v in first.items() if k != "replayed"} == {k: v for k, v in second.items() if k != "replayed"}
        assert work.get_record(db, scope["tenant"]["id"], row["id"])["version"] == 2


def test_a_conflicting_decision_is_answered_with_the_receipt_that_won(scope):
    import factory
    with factory.connect() as db:
        other = factory.user(db, scope["tenant"])
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        row = record(db, scope, run)

        def defer(current):
            work.update_record(db, current, status="deferred")
            return {"status": "deferred"}

        work.decide(db, tenant_id=scope["tenant"]["id"], record_id=row["id"], version=row["version"],
                    actor_id=scope["operator"]["id"], action="nothing", apply=defer)
        for actor, action in ((other["id"], "nothing"), (scope["operator"]["id"], "retry")):
            with pytest.raises(ServiceError) as conflict:
                work.decide(db, tenant_id=scope["tenant"]["id"], record_id=row["id"], version=row["version"],
                            actor_id=actor, action=action, apply=defer)
            assert conflict.value.kind == "conflict"
            assert conflict.value.payload["receipt"]["status"] == "deferred"
        # A decision on a version that has since changed is stale.
        with pytest.raises(ServiceError) as stale:
            work.decide(db, tenant_id=scope["tenant"]["id"], record_id=row["id"], version=99,
                        actor_id=scope["operator"]["id"], action="nothing", apply=defer)
        assert stale.value.kind == "conflict"


def test_status_stays_small_for_a_month_of_statement_rows(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("statement_chunk", {"rows": [n * 100, n * 100 + 99]}) for n in range(13)])
        items = db.execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()
        for item in items:
            work.add_records(db, item, [{"kind": "statement_row", "source": {"row": n}, "status": "proposed",
                                         "facts": {"narration": "INF/NEFT/" + "X" * 120}} for n in range(100)])
        status = work.status(db, scope["tenant"]["id"], run["id"])
        assert status["records"]["proposed"] == 1300 and status["items"]["queued"] == 13
        assert len(json.dumps(status, default=str).encode()) < 50_000
        page = work.records_page(db, scope["tenant"]["id"], run["id"], limit=100,
                                 summarize=lambda r: {"id": str(r["id"]), "status": r["status"]})
        assert len(page["records"]) == 100 and page["next"] is not None
        assert len(json.dumps(page, default=str).encode()) < 50_000


def test_a_running_item_counts_toward_its_tasks_active_processing_time(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        item = work.claim(db, kinds=("bill",), tenant_id=scope["tenant"]["id"])
        assert db.execute("SELECT processing_started_at FROM tasks WHERE id=%s", (run["task_id"],)).fetchone()[
            "processing_started_at"] is not None
        work.finish(db, item["id"], item["lease_token"], "done")
        task = db.execute("SELECT processing_started_at,processing_seconds FROM tasks WHERE id=%s",
                          (run["task_id"],)).fetchone()
        assert task["processing_started_at"] is None and task["processing_seconds"] >= 0


def test_the_run_state_follows_its_items_and_records(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"}, waiting_on={"kind": "sync", "ref": "pc"})])
        assert work.refresh(db, scope["tenant"]["id"], run["id"]) == "preparing"
        work.release(db, scope["tenant"]["id"], {"kind": "sync", "ref": "pc"})
        assert work.refresh(db, scope["tenant"]["id"], run["id"]) == "running"
        item = work.claim(db, kinds=("bill",), tenant_id=scope["tenant"]["id"])
        work.add_records(db, item, [{"kind": "bill", "source": {"file_id": "a"}, "status": "held",
                                     "hold_codes": ["classification_uncertain"]}])
        work.finish(db, item["id"], item["lease_token"], "done")
        assert work.refresh(db, scope["tenant"]["id"], run["id"]) == "review"
        task = db.execute("SELECT status FROM tasks WHERE id=%s", (run["task_id"],)).fetchone()
        assert task["status"] == "attention"
        row = db.execute("SELECT * FROM run_records WHERE run_id=%s", (run["id"],)).fetchone()
        work.update_record(db, row, status="saved")
        assert work.refresh(db, scope["tenant"]["id"], run["id"]) == "completed"


def test_a_run_summary_counts_its_work_in_its_workflows_words():
    """The task's one line counts what waits as the review does, in the singular and plural."""
    bills = work.Wording(input=("file", "files"), entry=("bill", "bills"), destination="Tally")
    items, records = dict.fromkeys(work.ITEM_STATES, 0), dict.fromkeys(work.RECORD_STATUSES, 0)
    assert work.describe_run("running", items | {"done": 1, "running": 2}, records, bills) == ("1 of 3 files read.", 23)
    review = lambda **counts: work.describe_run("review", items, records | counts, bills)[0]  # noqa: E731
    assert review(held=1, proposed=2) == "1 bill needs a decision; 2 ready to approve."
    assert review(held=3) == "3 bills need a decision."
    assert review(proposed=1, approved=2) == "1 bill ready to approve; 2 approved."
    done = lambda **counts: work.describe_run("completed", items, records | counts, bills)[0]  # noqa: E731
    assert done(saved=8, duplicate=2, deferred=1) == "8 bills saved in Tally; 2 already in Tally; 1 left as is."
    assert done() == "No bills entered."
    # A task title names its first input and counts the rest, never cut mid-name.
    assert work.title("Bill entry", ["01.pdf"]) == "Bill entry: 01.pdf"
    assert work.title("Bill entry", [f"{n:02}.pdf" for n in range(1, 16)]) == "Bill entry: 01.pdf and 14 more"


def test_an_unchanged_refresh_writes_no_timeline_event(scope):
    import factory
    with factory.connect() as db:
        run = launch(db, scope, [work.ItemSpec("bill", {"file_id": "a"})])
        count = lambda: db.execute("SELECT count(*) AS n FROM task_events WHERE task_id=%s",  # noqa: E731
                                   (run["task_id"],)).fetchone()["n"]
        work.refresh(db, scope["tenant"]["id"], run["id"])
        events = count()
        work.refresh(db, scope["tenant"]["id"], run["id"])
        work.refresh(db, scope["tenant"]["id"], run["id"])
        assert count() == events
