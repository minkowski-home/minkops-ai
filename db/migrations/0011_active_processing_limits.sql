-- Count elapsed active work once per task, even with parallel AI/native jobs.
-- Review, queue and explicit pauses do not consume this budget. These triggers
-- cover future workflows that use the shared runtime and desktop job contracts.
ALTER TABLE tasks ADD COLUMN processing_seconds double precision NOT NULL DEFAULT 0 CHECK (processing_seconds >= 0);
ALTER TABLE tasks ADD COLUMN processing_started_at timestamptz;
ALTER TABLE tasks ADD COLUMN stop_reason text;

CREATE FUNCTION refresh_task_processing_clock(scope uuid, task_key uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE current_task tasks; working boolean; instant timestamptz;
BEGIN
    SELECT * INTO current_task FROM tasks WHERE tenant_id=scope AND id=task_key FOR NO KEY UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    instant := clock_timestamp();
    working := current_task.control_state='active' AND (
        EXISTS (SELECT 1 FROM workflow_runs WHERE tenant_id=scope AND task_id=task_key
            AND state='executing' AND NOT coalesce((config->>'batch')::boolean,false)
            AND (NOT config ? 'tally_context_job_id' OR EXISTS (
                SELECT 1 FROM desktop_jobs WHERE tenant_id=scope AND id::text=workflow_runs.config->>'tally_context_job_id'
                    AND state IN ('completed','failed'))))
        OR EXISTS (SELECT 1 FROM desktop_jobs WHERE tenant_id=scope AND task_id=task_key AND state='executing'));
    IF working AND current_task.processing_started_at IS NULL THEN
        UPDATE tasks SET processing_started_at=instant WHERE id=task_key;
    ELSIF NOT working AND current_task.processing_started_at IS NOT NULL THEN
        UPDATE tasks SET processing_seconds=processing_seconds+greatest(0,extract(epoch FROM instant-processing_started_at)),
            processing_started_at=NULL WHERE id=task_key;
    END IF;
END $$;

CREATE FUNCTION task_processing_clock_changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='tasks' THEN
        PERFORM refresh_task_processing_clock(NEW.tenant_id,NEW.id);
    ELSE
        PERFORM refresh_task_processing_clock(NEW.tenant_id,NEW.task_id);
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER workflow_processing_clock AFTER INSERT OR UPDATE OF state,config ON workflow_runs
    FOR EACH ROW EXECUTE FUNCTION task_processing_clock_changed();
CREATE TRIGGER desktop_processing_clock AFTER INSERT OR UPDATE OF state ON desktop_jobs
    FOR EACH ROW EXECUTE FUNCTION task_processing_clock_changed();
CREATE TRIGGER paused_processing_clock AFTER UPDATE OF control_state ON tasks
    FOR EACH ROW WHEN (NEW.control_state IS DISTINCT FROM OLD.control_state) EXECUTE FUNCTION task_processing_clock_changed();
CREATE INDEX tasks_processing_clock_idx ON tasks(processing_started_at)
    WHERE control_state='active' AND status NOT IN ('completed','failed');

-- Existing work starts its measured budget at upgrade, never retroactively.
DO $$ DECLARE task_row record; BEGIN
    FOR task_row IN SELECT tenant_id,id FROM tasks WHERE control_state='active' AND status NOT IN ('completed','failed') LOOP
        PERFORM refresh_task_processing_clock(task_row.tenant_id,task_row.id);
    END LOOP;
END $$;
