"""Bounded hosting of the existing worker, with transactional coalesced wake-ups.

Cloud notifications may be lost or duplicated. PostgreSQL remains authoritative:
generation checks prevent a finishing job from consuming a later notification,
and a runner lock bounds overlap. The existing per-run locks/session IDs retain
paid-execution recovery. An hourly sweep recovers failed notifications/crashes.
"""

import logging
import time
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


def drain(url, *, max_seconds=1200, work=None, cleanup=None):
    from .accounts.worker import work_once, cleanup_once

    work, cleanup = work or work_once, cleanup or cleanup_once
    deadline, processed = time.monotonic() + max_seconds, 0
    released = False
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as c:
        if not c.execute("SELECT pg_try_advisory_lock(%s) AS held", (RUNNER_LOCK,)).fetchone()[
            "held"
        ]:
            return 0
        try:
            while time.monotonic() < deadline:
                observed = c.execute("SELECT generation FROM worker_wakeup").fetchone()[
                    "generation"
                ]
                c.execute("UPDATE worker_wakeup SET lease_until=now()+interval '30 minutes'")
                if work(url):
                    processed += 1
                    continue
                if cleanup(url):
                    continue
                with c.transaction():
                    current = c.execute(
                        "SELECT generation FROM worker_wakeup FOR UPDATE"
                    ).fetchone()["generation"]
                    if current != observed:
                        continue
                    c.execute(
                        "UPDATE worker_wakeup SET acknowledged=%s,lease_until=NULL,dispatch_token=NULL",
                        (current,),
                    )
                    # Release while holding the notification row. A dispatcher
                    # cannot start a successor until this acknowledgement commits.
                    c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))
                    released = True
                    return processed
            # Preserve runnable work for a successor when this bounded slice ends.
            c.execute("UPDATE worker_wakeup SET generation=generation+1")
            return processed
        finally:
            if not released:
                with c.transaction():
                    c.execute("UPDATE worker_wakeup SET lease_until=NULL,dispatch_token=NULL")
                    c.execute("SELECT pg_advisory_unlock(%s)", (RUNNER_LOCK,))
