"""Small durable database worker for the managed hosted agent sessions.

PostgreSQL owns the queue and run state; OpenAI owns tool use and reasoning.
Advisory locks prevent duplicate workers. A saved session is reconciled after
worker restart without replaying the user's task. Ambiguous creation failures
are surfaced for explicit intervention, never automatically resubmitted.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from minkops_platform.runtime import application, lifecycle

from .agent import close_session, execute
from .run_store import AccountsRunStore

STORE = AccountsRunStore()


def process(connection, run, *, executor=execute):
    application.process(
        connection,
        STORE,
        run,
        executor=executor,
        close_session=close_session,
        cleanup=executor is execute,
    )


def work_once(url, *, executor=execute):
    from .batch import reconcile_once

    reconcile_once(url)
    worked = lifecycle.work_once(
        url, STORE, lambda connection, run: process(connection, run, executor=executor)
    )
    reconcile_once(url)
    return worked


def run_forever(url):
    def lane():
        while True:
            if not work_once(url):
                cleanup_once(url)
                time.sleep(2)

    # Each lane owns a database connection; persisted runs/locks remain the
    # source of truth for recovery, including independent paid child sessions.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(lane) for _ in range(4)]
        for future in futures:
            future.result()


def cleanup_once(url):
    """Retry terminal-run environment cleanup through the shared lifecycle."""
    lifecycle.cleanup_once(url, STORE, close_session=close_session)
