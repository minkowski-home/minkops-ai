"""One durable active-time budget for every shared workflow and native task.

The database measures the union of active operations; worker monitors and API
polls enforce the deadline independently of a model's stream or responsiveness.
Timeouts use the ordinary Stop fences, never kill an uncertain financial save.
"""
import logging
import os
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)


def limit_minutes():
    try:
        minutes = int(os.getenv('MINKOPS_RUN_TIMEOUT_MINUTES', '45'))
    except ValueError as error:
        raise ValueError('MINKOPS_RUN_TIMEOUT_MINUTES must be an integer from 1 to 1440.') from error
    if not 1 <= minutes <= 1440:
        raise ValueError('MINKOPS_RUN_TIMEOUT_MINUTES must be an integer from 1 to 1440.')
    return minutes


def overdue(task, minutes=None):
    if task['control_state'] != 'active' or task['status'] in ('completed','failed'):
        return False
    seconds = task['processing_seconds']
    if task['processing_started_at']:
        seconds += max(0, (datetime.now(UTC)-task['processing_started_at']).total_seconds())
    return seconds >= (minutes if minutes is not None else limit_minutes())*60


def expire(connection):
    """Caller owns the transaction. Recheck after the normal run→task locks."""
    from .run_controls import _task_control
    minutes = limit_minutes()
    rows = connection.execute('''SELECT tenant_id,id FROM tasks WHERE control_state='active'
        AND status NOT IN ('completed','failed') AND processing_seconds+
        coalesce(greatest(0,extract(epoch FROM clock_timestamp()-processing_started_at)),0) >= %s
        ORDER BY id LIMIT 100''',(minutes*60,)).fetchall()
    stopped = 0
    for row in rows:
        try:
            # A receipt or approval may hold the normal run/task locks. Skip
            # that task for this tick without failing unrelated API requests.
            with connection.transaction():
                task = _task_control(connection,row['tenant_id'],None,row['id'],'stop',timeout_minutes=minutes)
                stopped += task['control_state'] == 'stopped'
        except psycopg.errors.LockNotAvailable:
            log.info('Run limit check deferred for busy task %s', row['id'])
    return stopped


def enforce(url, *, cancel=True):
    """Commit stop intent before provider I/O; failed cancellation stays retryable."""
    with psycopg.connect(url,connect_timeout=5,row_factory=dict_row) as connection:
        connection.execute("SET LOCAL lock_timeout='1s'")
        count = expire(connection)
        connection.commit()
        if cancel:
            pending = connection.execute("SELECT * FROM workflow_runs WHERE config @> '{\"timeout_cancel_pending\":true}' AND session_id IS NOT NULL ORDER BY updated_at LIMIT 4").fetchall()
            connection.commit()
            from .runtime.openai_hosted import cancel_turn
            from .runtime.diagnostics import record
            for run in pending:
                try:
                    cancel_turn(run['session_id'],run['turn_id'])
                    connection.execute("UPDATE workflow_runs SET config=config || '{\"timeout_cancel_pending\":false}' WHERE id=%s",(run['id'],))
                    connection.commit()
                    record(connection,run,'runtime.cancelled','Requested cancellation after active processing limit.')
                except Exception as error:
                    connection.rollback()
                    # Rotate failures behind other pending cancellations.
                    connection.execute('UPDATE workflow_runs SET updated_at=now() WHERE id=%s',(run['id'],))
                    connection.commit()
                    log.warning('Timed-out run cancellation pending for %s (%s)',run['id'],type(error).__name__)
        return count
