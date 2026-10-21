"""Bounded hosting of the worker, with transactional coalesced wake-ups.

Cloud notifications may be lost or duplicated. PostgreSQL remains
authoritative: generation checks keep a finishing worker from consuming a
later notification, and a runner lock bounds overlap. Run items carry their
own leases and provider session IDs, so a paid session survives a restart
(lanes.py). A private five-minute sweep repairs lost notifications and crashes.
"""

import logging
import time
from threading import Lock
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from . import work
from .run_limits import enforce

log = logging.getLogger(__name__)
RUNNER_LOCK = 481913
# How long a drain or a long-running worker waits between checks of its lanes and of run limits.
TICK_SECONDS = 10
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
    """Cheap watchdog: repair a lost wake only when there is work for a worker.

    A live runner owns the advisory lock. A recently reserved launch gets two
    minutes to start before its abandoned lease can be replaced. Item leases
    and stored provider session identities still control actual execution.
    """
    with psycopg.connect(url, row_factory=dict_row) as c:
        if not c.execute('SELECT pg_try_advisory_xact_lock(%s) AS held', (RUNNER_LOCK,)).fetchone()['held']:
            return False
        row = c.execute("""SELECT lease_until>clock_timestamp()+interval '28 minutes' AS starting
            FROM worker_wakeup FOR UPDATE""").fetchone()
        # A session finished within the hour still holds its usage to record; older ones expire on their own.
        if row['starting'] or not (work.runnable(c) or work.unclosed(c, limit=1, within=3600)):
            return False
        c.execute("""UPDATE worker_wakeup SET generation=greatest(generation,acknowledged+1),
            lease_until=NULL,dispatch_token=NULL""")
    return dispatch(url, submit)


def monitor(url):
    """Stop tasks past their active-time budget; a database outage is retried on the next tick."""
    try:
        enforce(url)
    except psycopg.Error as error:
        log.warning('Run limit monitor will retry (%s)', type(error).__name__)


def serve(url):
    """Enforce run limits while an entered lanes host serves, until the process ends."""
    while True:
        monitor(url)
        time.sleep(TICK_SECONDS)


def drain(url, host, *, max_seconds=1200):
    """Serve run items until settled, then acknowledge the wake-up generation that was observed.

    `host` is an entered lanes.Host; it is settled when no lane is busy,
    nothing is runnable and its finished sessions are closed with their usage
    recorded. At the deadline the host stops claiming and the generation is
    bumped for a successor; the caller's exit hands the sessions still held to it.
    """
    deadline = time.monotonic() + max_seconds
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as c:
        if not c.execute("SELECT pg_try_advisory_lock(%s) AS held", (RUNNER_LOCK,)).fetchone()["held"]:
            return False
        acknowledged = False
        try:
            while time.monotonic() < deadline:
                # Publish the runner lease first, so dispatchers never see active work without it.
                c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes'")
                observed = c.execute("SELECT generation FROM worker_wakeup").fetchone()["generation"]
                monitor(url)
                if not host.wait_idle(TICK_SECONDS):
                    continue
                with c.transaction():
                    current = c.execute("SELECT generation FROM worker_wakeup FOR UPDATE").fetchone()["generation"]
                    if current == observed and host.settled(c):
                        c.execute("UPDATE worker_wakeup SET acknowledged=%s,lease_until=NULL,dispatch_token=NULL",
                                  (current,))
                        acknowledged = True
                        return True
                # Something is still to do: a lane wakes for it, or a session closes within a tick.
                time.sleep(1)
            host.stop_claiming()
            # Preserve runnable work for a successor when this bounded slice ends.
            c.execute("UPDATE worker_wakeup SET generation=generation+1")
            return False
        finally:
            if not acknowledged:
                # A successor may be dispatched at once, not after this lease would have lapsed.
                c.execute("UPDATE worker_wakeup SET lease_until=NULL,dispatch_token=NULL")
            c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))
