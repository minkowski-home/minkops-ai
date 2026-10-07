"""Small durable database worker for the managed hosted agent sessions.

PostgreSQL owns the queue and run state; OpenAI owns tool use and reasoning.
Advisory locks prevent duplicate workers. A saved session is reconciled after
worker restart without replaying the user's task. Ambiguous creation failures
are surfaced for explicit intervention, never automatically resubmitted.
"""

import time

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
    return lifecycle.work_once(
        url, STORE, lambda connection, run: process(connection, run, executor=executor)
    )


def run_forever(url):
    while True:
        if not work_once(url):
            cleanup_once(url)
            time.sleep(2)


def cleanup_once(url):
    """Retry terminal-run environment cleanup through the shared lifecycle."""
    lifecycle.cleanup_once(url, STORE, close_session=close_session)
