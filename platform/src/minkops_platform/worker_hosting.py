"""Bounded hosting of the existing worker, with transactional coalesced wake-ups.

Cloud notifications may be lost or duplicated. PostgreSQL remains authoritative:
generation checks prevent a finishing job from consuming a later notification,
and a runner lock bounds overlap. The existing per-run locks/session IDs retain
paid-execution recovery. A private five-minute sweep recovers lost notifications/crashes.
"""

import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Lock
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)
RUNNER_LOCK = 481913
_DISPATCH_LOCK = Lock()


def dispatch(url, submit):
    # Response background tasks can outlive Cloud Run's request concurrency
    # accounting. Coalesce within the API process before opening a DB socket.
    if not _DISPATCH_LOCK.acquire(blocking=False):
        return False
    try:
        return _dispatch(url, submit)
    except psycopg.Error as error:
        log.warning('Worker dispatch pending (%s)', type(error).__name__)
        return False
    finally:
        _DISPATCH_LOCK.release()


def _dispatch(url, submit):
    token = uuid4()
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=5,
                         options='-c lock_timeout=1000') as c:
        row = c.execute("SELECT * FROM worker_wakeup FOR UPDATE").fetchone()
        if (
            row["generation"] <= row["acknowledged"]
            or c.execute("SELECT coalesce(%s > now(),false)", (row["lease_until"],)).fetchone()[
                "coalesce"
            ]
        ):
            return False
        c.execute(
            "UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes',dispatch_token=%s",
            (token,),
        )
        c.commit()
        try:
            submit()
            return True
        except Exception as error:
            # Failed dispatch leaves the generation pending; the next request or
            # recovery sweep retries. Ambiguous duplicates cannot run together.
            c.execute(
                "UPDATE worker_wakeup SET lease_until=NULL,dispatch_token=NULL WHERE dispatch_token=%s",
                (token,),
            )
            log.warning("Worker dispatch pending (%s)", type(error).__name__)
            return False


def recover(url, submit):
    """Cheap watchdog: repair a lost wake only when recoverable work exists.

    A live runner owns the advisory lock. A recently reserved launch gets two
    minutes to start before its abandoned lease can be replaced. Per-run locks
    and persisted provider session identities still control actual execution.
    """
    with psycopg.connect(url, row_factory=dict_row) as c:
        if not c.execute('SELECT pg_try_advisory_xact_lock(%s) AS held', (RUNNER_LOCK,)).fetchone()['held']:
            return False
        row = c.execute("""SELECT *,lease_until>clock_timestamp()+interval '28 minutes' AS starting
            FROM worker_wakeup FOR UPDATE""").fetchone()
        if row['starting']:
            return False
        needed = c.execute("""SELECT EXISTS (
            SELECT 1 FROM workflow_runs r JOIN tasks t ON t.tenant_id=r.tenant_id AND t.id=r.task_id
            WHERE t.control_state='active' AND NOT r.superseded AND r.state IN ('queued','executing')
                AND NOT r.blocked
                AND (r.context_job_id IS NULL OR EXISTS (SELECT 1 FROM desktop_jobs j
                    WHERE j.tenant_id=r.tenant_id AND j.id::text=r.context_job_id AND j.state IN ('completed','failed')))
                AND (NOT r.is_batch OR EXISTS (SELECT 1 FROM workflow_runs child
                    WHERE child.tenant_id=r.tenant_id AND child.parent_run_id=r.id AND NOT child.superseded
                        AND child.state IN ('review','failed') AND child.updated_at>r.updated_at))
            UNION ALL
            SELECT 1 FROM workflow_runs WHERE session_id IS NOT NULL AND (
                cancel_pending OR (state NOT IN ('queued','executing') AND NOT session_closed
                    AND cleanup_attempt_count<10 AND coalesce(cleanup_attempt_at,'epoch')<now()-interval '1 minute'))
            ) AS needed""").fetchone()['needed']
        if not needed:
            return False
        c.execute("""UPDATE worker_wakeup SET generation=greatest(generation,acknowledged+1),
            lease_until=NULL,dispatch_token=NULL""")
    return dispatch(url, submit)


def drain(url, *, max_seconds=1200, work=None, cleanup=None, lanes=None):
    from .accounts.worker import WORKER_LANES, cleanup_once, work_once

    work, cleanup = work or work_once, cleanup or cleanup_once
    lanes = WORKER_LANES if lanes is None else lanes
    if not isinstance(lanes, int) or isinstance(lanes, bool) or not 1 <= lanes <= WORKER_LANES:
        raise ValueError(f"Worker lanes must be between 1 and {WORKER_LANES}.")
    deadline, processed = time.monotonic() + max_seconds, 0
    released = False
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as c:
        if not c.execute("SELECT pg_try_advisory_lock(%s) AS held", (RUNNER_LOCK,)).fetchone()[
            "held"
        ]:
            return 0
        try:
            # Keep the global lock until all lane futures finish. Each worker
            # owns its connection and retains the existing per-run advisory lock.
            # One maintenance slot never consumes an AI proposal lane. Its
            # durable cleanup claim remains bounded independently of AI work.
            with ThreadPoolExecutor(max_workers=lanes + 1) as pool:
                processed, released = _drain_lanes(c, pool, url, work, cleanup, lanes, deadline)
            if released:
                return processed
            # Preserve runnable work for a successor when this bounded slice ends.
            c.execute("UPDATE worker_wakeup SET generation=generation+1")
            return processed
        finally:
            if not released:
                with c.transaction():
                    c.execute("UPDATE worker_wakeup SET lease_until=NULL,dispatch_token=NULL")
                    c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))


def _drain_lanes(c, pool, url, work, cleanup, lanes, deadline):
    processed = 0
    pending = set()
    observed = None
    maintenance = None
    next_cleanup = 0
    idle = False
    while time.monotonic() < deadline or pending or maintenance:
        from .run_limits import enforce
        try:
            enforce(url)
        except psycopg.Error as error:
            log.warning('Run limit monitor will retry (%s)',type(error).__name__)
        # A lane can run immediately after submit. Publish the runner lease first
        # so dispatchers never observe active work without its coalescing lease.
        c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes'")
        if maintenance and maintenance.done() and pending:
            maintenance.result()
            maintenance = None
            next_cleanup = time.monotonic() + 2
        if not pending and not idle:
            if time.monotonic() >= deadline:
                break
            observed = c.execute("SELECT generation FROM worker_wakeup").fetchone()["generation"]
            pending = {pool.submit(work, url) for _ in range(lanes)}
        if maintenance is None and (idle or time.monotonic() >= next_cleanup):
            maintenance = pool.submit(cleanup, url)
        targets = pending | ({maintenance} if maintenance else set())
        done, _ = wait(targets, timeout=10, return_when=FIRST_COMPLETED)
        finished = done & pending
        pending -= finished
        worked = sum(bool(future.result()) for future in finished)
        processed += worked
        if worked and time.monotonic() < deadline:
            pending.update(pool.submit(work, url) for _ in range(lanes - len(pending)))
        idle = not pending
        if pending:
            continue
        if time.monotonic() >= deadline:
            break
        # Give committed results a chance to reconcile while close/retry runs
        # in maintenance. An idle runner must finish this check before ack.
        if maintenance is None or not maintenance.done():
            continue
        cleaned = maintenance.result()
        maintenance = None
        if cleaned:
            idle = False
            continue
        # No lane can still be running when we acknowledge this generation.
        with c.transaction():
            current = c.execute("SELECT generation FROM worker_wakeup FOR UPDATE").fetchone()[
                "generation"
            ]
            if current != observed:
                idle = False
                continue
            c.execute(
                "UPDATE worker_wakeup SET acknowledged=%s,lease_until=NULL,dispatch_token=NULL",
                (current,),
            )
            c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))
            return processed, True
    return processed, False
