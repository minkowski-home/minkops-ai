-- A run can stay queued while its PC supplies required Tally context. The first
-- worker may already have acknowledged that run's insert; terminal context jobs
-- must therefore create a new durable wake even when the run's state is unchanged.
-- Replayed completion receipts do not change the job state and emit no wake.
CREATE TRIGGER tally_context_worker_wakeup
AFTER UPDATE OF state ON desktop_jobs
FOR EACH ROW
WHEN (NEW.operation = 'tally.references'
      AND NEW.state IN ('completed', 'failed')
      AND NEW.state IS DISTINCT FROM OLD.state)
EXECUTE FUNCTION notify_workflow_worker();
