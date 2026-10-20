"""Small durable database worker for the managed hosted agent sessions.

PostgreSQL owns the queue and run state; OpenAI owns tool use and reasoning.
Advisory locks prevent duplicate workers. A saved session is reconciled after
worker restart without replaying the user's task. Ambiguous creation failures
are surfaced for explicit intervention, never automatically resubmitted.
"""

import logging
import time
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait

import psycopg

from minkops_platform.runtime import application, lifecycle
from minkops_platform.runtime.store import WorkflowRunStore

from .agent import close_session, execute

STORE = WorkflowRunStore()
WORKER_LANES = 4
log = logging.getLogger(__name__)


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


def run_forever(url, *, lanes=WORKER_LANES):
    if type(lanes) is not int or not 1 <= lanes <= WORKER_LANES:
        raise ValueError(f'Worker lanes must be between 1 and {WORKER_LANES}.')
    def lane():
        while True:
            if not work_once(url):
                cleanup_once(url)
                time.sleep(2)

    # Each lane owns a database connection; persisted runs/locks remain the
    # source of truth for recovery, including independent paid child sessions.
    with ThreadPoolExecutor(max_workers=lanes) as pool:
        futures = [pool.submit(lane) for _ in range(lanes)]
        while True:
            done, _ = wait(futures,timeout=10,return_when=FIRST_EXCEPTION)
            for future in done:
                future.result()
            from minkops_platform.run_limits import enforce
            try:
                enforce(url)
            except psycopg.Error as error:
                log.warning('Run limit monitor will retry (%s)',type(error).__name__)


def cleanup_once(url):
    """Retry terminal-run environment cleanup through the shared lifecycle."""
    return lifecycle.cleanup_once(url, STORE, close_session=close_session)
