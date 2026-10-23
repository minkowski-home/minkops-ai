-- The staged pipeline, Source Discovery and the hosted-environment runtime left
-- the code during the accounts desk rebuild. Their tables, the compatibility
-- view over them, and the triggers and functions that served them go too.
--
-- The rebuilt app starts on a fresh database (docs/rebuild/cutover.md); the
-- parked build keeps its own. A database still holding the old build's work
-- refuses this migration, so its history is never dropped.
DO $$
DECLARE legacy text; present boolean;
BEGIN
    FOREACH legacy IN ARRAY ARRAY['workflow_runs', 'discovery_runs', 'account_writes', 'account_tally_writes',
                                  'account_catalogs', 'workflow_run_assets'] LOOP
        IF to_regclass(legacy) IS NOT NULL THEN
            -- EXECUTE leaves FOUND alone, so the answer is selected.
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I)', legacy) INTO present;
            IF present THEN
                RAISE EXCEPTION 'This database holds the parked build''s work (%): the rebuilt app starts on a fresh database.', legacy;
            END IF;
        END IF;
    END LOOP;
END $$;

-- The task clock counts native jobs and run items only.
CREATE OR REPLACE FUNCTION refresh_task_processing_clock(scope uuid, task_key uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE current_task tasks; working boolean; instant timestamptz;
BEGIN
    SELECT * INTO current_task FROM tasks WHERE tenant_id=scope AND id=task_key FOR NO KEY UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    instant := clock_timestamp();
    working := current_task.control_state='active' AND (
        EXISTS (SELECT 1 FROM desktop_jobs WHERE tenant_id=scope AND task_id=task_key AND state='executing')
        OR EXISTS (SELECT 1 FROM run_items WHERE tenant_id=scope AND task_id=task_key AND state='running'));
    IF working AND current_task.processing_started_at IS NULL THEN
        UPDATE tasks SET processing_started_at=instant WHERE id=task_key;
    ELSIF NOT working AND current_task.processing_started_at IS NOT NULL THEN
        UPDATE tasks SET processing_seconds=processing_seconds+greatest(0,extract(epoch FROM instant-processing_started_at)),
            processing_started_at=NULL WHERE id=task_key;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION task_processing_clock_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='tasks' THEN
        PERFORM refresh_task_processing_clock(NEW.tenant_id, NEW.id);
    ELSE
        PERFORM refresh_task_processing_clock(NEW.tenant_id, NEW.task_id);
    END IF;
    RETURN NEW;
END $$;

-- Run items wake workers when queued (run_item_queued); a native job changing never needs to.
DROP TRIGGER IF EXISTS tally_context_worker_wakeup ON desktop_jobs;

DROP VIEW IF EXISTS account_runs;
DROP TABLE IF EXISTS workflow_run_asset_refs, workflow_run_assets, workflow_run_diagnostics, hosted_environment_slots,
    account_tally_writes, account_writes, discovery_runs, workflow_runs, account_catalogs;
DROP FUNCTION IF EXISTS notify_workflow_worker(), pin_workflow_assets(), immutable_workflow_asset(),
    discovery_catalog_changed();
