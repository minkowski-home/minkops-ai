"""Bounded hosting of the existing worker, with transactional coalesced wake-ups.

Cloud notifications may be lost or duplicated. PostgreSQL remains authoritative:
generation checks prevent a finishing job from consuming a later notification,
and a runner lock bounds overlap. The existing per-run locks/session IDs retain
paid-execution recovery. An hourly sweep recovers failed notifications/crashes.
"""

import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)
RUNNER_LOCK = 481913


def dispatch(url, submit):
    token = uuid4()
    with psycopg.connect(url, row_factory=dict_row) as c:
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
            with ThreadPoolExecutor(max_workers=lanes) as pool:
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
    while time.monotonic() < deadline or pending:
        if not pending:
            if time.monotonic() >= deadline:
                break
            observed = c.execute("SELECT generation FROM worker_wakeup").fetchone()["generation"]
            pending = {pool.submit(work, url) for _ in range(lanes)}
        c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes'")
        done, pending = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
        worked = sum(bool(future.result()) for future in done)
        processed += worked
        if worked and time.monotonic() < deadline:
            pending.update(pool.submit(work, url) for _ in range(lanes - len(pending)))
        if pending:
            continue
        if time.monotonic() >= deadline:
            break
        if cleanup(url):
            continue
        # No lane can still be running when we acknowledge this generation.
        with c.transaction():
            current = c.execute("SELECT generation FROM worker_wakeup FOR UPDATE").fetchone()[
                "generation"
            ]
            if current != observed:
                continue
            c.execute(
                "UPDATE worker_wakeup SET acknowledged=%s,lease_until=NULL,dispatch_token=NULL",
                (current,),
            )
            c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))
            return processed, True
    return processed, False
