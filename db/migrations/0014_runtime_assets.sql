-- Keep immutable, often multi-megabyte execution evidence away from frequently
-- rewritten scheduling metadata. Assets are deduplicated only within a tenant;
-- the SHA is identity, never an authorization grant.
CREATE TABLE workflow_run_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    field text NOT NULL,
    sha256 text NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id,field,sha256),
    UNIQUE (tenant_id,id)
);

CREATE FUNCTION immutable_workflow_asset() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Pinned workflow assets cannot be updated';
END $$;
CREATE TRIGGER workflow_asset_immutable BEFORE UPDATE ON workflow_run_assets
    FOR EACH ROW EXECUTE FUNCTION immutable_workflow_asset();

CREATE TABLE workflow_run_asset_refs (
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    field text NOT NULL,
    asset_id uuid NOT NULL,
    PRIMARY KEY (tenant_id,run_id,field),
    FOREIGN KEY (tenant_id,run_id) REFERENCES workflow_runs(tenant_id,id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (tenant_id,asset_id) REFERENCES workflow_run_assets(tenant_id,id)
);

ALTER TABLE workflow_runs ADD COLUMN is_batch boolean NOT NULL DEFAULT false;
ALTER TABLE workflow_runs ADD COLUMN blocked boolean NOT NULL DEFAULT false;
ALTER TABLE workflow_runs ADD COLUMN awaited_profile_id text;
ALTER TABLE workflow_runs ADD COLUMN awaited_layout_run_id text;
ALTER TABLE workflow_runs ADD COLUMN context_job_id text;
ALTER TABLE workflow_runs ADD COLUMN execution_stage text;
ALTER TABLE workflow_runs ADD COLUMN superseded boolean NOT NULL DEFAULT false;
ALTER TABLE workflow_runs ADD COLUMN expanded boolean NOT NULL DEFAULT false;
ALTER TABLE workflow_runs ADD COLUMN session_closed boolean NOT NULL DEFAULT false;
ALTER TABLE workflow_runs ADD COLUMN cleanup_attempt_at timestamptz;
ALTER TABLE workflow_runs ADD COLUMN cleanup_attempt_count integer NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN cancel_pending boolean NOT NULL DEFAULT false;

CREATE FUNCTION pin_workflow_assets() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE field_name text; digest text; asset uuid; asset_refs jsonb;
BEGIN
    asset_refs := coalesce(NEW.config->'_assets','{}'::jsonb);
    FOREACH field_name IN ARRAY ARRAY['execution_snapshot','instructions_snapshot','agent_output_schema',
        'source_catalog_snapshot','catalog_snapshot','local_discovery_snapshot','statement_context'] LOOP
        IF NEW.config ? field_name THEN
            digest := encode(sha256(convert_to((NEW.config->field_name)::text,'UTF8')),'hex');
            INSERT INTO workflow_run_assets(tenant_id,field,sha256,content)
                VALUES(NEW.tenant_id,field_name,digest,NEW.config->field_name)
                ON CONFLICT (tenant_id,field,sha256) DO NOTHING;
            SELECT id INTO asset FROM workflow_run_assets
                WHERE tenant_id=NEW.tenant_id AND field=field_name AND sha256=digest;
            asset_refs := asset_refs || jsonb_build_object(field_name,asset::text);
            NEW.config := NEW.config-field_name;
        END IF;
    END LOOP;
    -- An old/new application can copy a pinned config, but cannot bind another
    -- tenant's evidence or relabel an asset as a different execution field.
    IF EXISTS (SELECT 1 FROM jsonb_each_text(asset_refs) r WHERE NOT EXISTS
        (SELECT 1 FROM workflow_run_assets a WHERE a.tenant_id=NEW.tenant_id
            AND a.id::text=r.value AND a.field=r.key)) THEN
        RAISE EXCEPTION 'Workflow asset is outside the run scope';
    END IF;
    IF TG_OP='INSERT' OR asset_refs IS DISTINCT FROM coalesce(OLD.config->'_assets','{}'::jsonb) THEN
        DELETE FROM workflow_run_asset_refs WHERE tenant_id=NEW.tenant_id AND run_id=NEW.id
            AND NOT asset_refs ? field;
        INSERT INTO workflow_run_asset_refs(tenant_id,run_id,field,asset_id)
            SELECT NEW.tenant_id,NEW.id,key,value::uuid FROM jsonb_each_text(asset_refs)
            ON CONFLICT (tenant_id,run_id,field) DO UPDATE SET asset_id=excluded.asset_id
                WHERE workflow_run_asset_refs.asset_id IS DISTINCT FROM excluded.asset_id;
    END IF;
    IF asset_refs <> '{}'::jsonb THEN
        NEW.config := NEW.config || jsonb_build_object('_assets',asset_refs);
    END IF;
    NEW.is_batch := coalesce((NEW.config->>'batch')::boolean,false);
    NEW.blocked := NEW.config ? 'awaits';
    NEW.awaited_profile_id := NEW.config#>>'{awaits,profile}';
    NEW.awaited_layout_run_id := NEW.config#>>'{awaits,layout_run}';
    NEW.context_job_id := NEW.config->>'tally_context_job_id';
    NEW.execution_stage := NEW.config->>'stage';
    NEW.superseded := coalesce((NEW.config->>'superseded')::boolean,false);
    NEW.expanded := coalesce((NEW.config->>'expanded')::boolean,false);
    NEW.session_closed := coalesce((NEW.config->>'hosted_session_closed')::boolean,false);
    NEW.cleanup_attempt_at := (NEW.config->>'cleanup_attempt_at')::timestamptz;
    NEW.cleanup_attempt_count := coalesce((NEW.config->>'cleanup_attempt_count')::integer,0);
    NEW.cancel_pending := coalesce((NEW.config->>'timeout_cancel_pending')::boolean,false);
    RETURN NEW;
END $$;
CREATE TRIGGER pin_workflow_assets BEFORE INSERT OR UPDATE OF config ON workflow_runs
    FOR EACH ROW EXECUTE FUNCTION pin_workflow_assets();

CREATE INDEX workflow_runs_candidates ON workflow_runs(updated_at,tenant_id,id)
    WHERE NOT is_batch AND NOT superseded AND NOT blocked AND state IN ('queued','executing');
CREATE INDEX workflow_runs_profile_waiters ON workflow_runs(tenant_id,awaited_profile_id)
    WHERE state='queued' AND awaited_profile_id IS NOT NULL;
CREATE INDEX workflow_runs_layout_waiters ON workflow_runs(tenant_id,awaited_layout_run_id)
    WHERE state='queued' AND awaited_layout_run_id IS NOT NULL;
CREATE INDEX workflow_runs_active_batches ON workflow_runs(updated_at,tenant_id,id)
    WHERE is_batch AND state IN ('queued','executing');
CREATE INDEX workflow_runs_cleanup ON workflow_runs(cleanup_attempt_at,updated_at)
    WHERE state NOT IN ('queued','executing') AND session_id IS NOT NULL
        AND NOT session_closed AND cleanup_attempt_count<10;

CREATE OR REPLACE FUNCTION refresh_task_processing_clock(scope uuid, task_key uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE current_task tasks; working boolean; instant timestamptz;
BEGIN
    SELECT * INTO current_task FROM tasks WHERE tenant_id=scope AND id=task_key FOR NO KEY UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    instant := clock_timestamp();
    working := current_task.control_state='active' AND (
        EXISTS (SELECT 1 FROM workflow_runs r WHERE r.tenant_id=scope AND r.task_id=task_key
            AND r.state='executing' AND NOT r.is_batch AND NOT r.superseded
            AND (r.context_job_id IS NULL OR EXISTS (SELECT 1 FROM desktop_jobs j
                WHERE j.tenant_id=scope AND j.id::text=r.context_job_id AND j.state IN ('completed','failed'))))
        OR EXISTS (SELECT 1 FROM desktop_jobs WHERE tenant_id=scope AND task_id=task_key AND state='executing'));
    IF working AND current_task.processing_started_at IS NULL THEN
        UPDATE tasks SET processing_started_at=instant WHERE id=task_key;
    ELSIF NOT working AND current_task.processing_started_at IS NOT NULL THEN
        UPDATE tasks SET processing_seconds=processing_seconds+greatest(0,extract(epoch FROM instant-processing_started_at)),
            processing_started_at=NULL WHERE id=task_key;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION task_processing_clock_changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='workflow_runs' AND TG_OP='UPDATE' THEN
        IF NEW.state IS NOT DISTINCT FROM OLD.state AND NEW.is_batch=OLD.is_batch
            AND NEW.superseded=OLD.superseded AND NEW.context_job_id IS NOT DISTINCT FROM OLD.context_job_id THEN
            RETURN NEW;
        END IF;
    END IF;
    IF TG_TABLE_NAME='tasks' THEN
        PERFORM refresh_task_processing_clock(NEW.tenant_id,NEW.id);
    ELSE
        PERFORM refresh_task_processing_clock(NEW.tenant_id,NEW.task_id);
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION notify_workflow_worker() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE wake boolean := false;
BEGIN
    IF TG_TABLE_NAME='desktop_jobs' THEN
        wake := true;
    ELSIF TG_OP='INSERT' THEN
        wake := NEW.state IN ('queued','executing');
    ELSE
        wake := NEW.state IS DISTINCT FROM OLD.state OR (
            NEW.state='queued' AND (
                (OLD.blocked AND NOT NEW.blocked)
                OR (OLD.context_job_id IS NOT NULL AND NEW.context_job_id IS NULL)));
    END IF;
    IF wake THEN UPDATE worker_wakeup SET generation=generation+1 WHERE singleton; END IF;
    RETURN NEW;
END $$;
DROP TRIGGER workflow_worker_wakeup ON workflow_runs;
CREATE TRIGGER workflow_worker_wakeup AFTER INSERT OR UPDATE OF state,config ON workflow_runs
    FOR EACH ROW EXECUTE FUNCTION notify_workflow_worker();

-- Preserve each existing run's original evidence. Install the narrow clock
-- trigger first so this upgrade does not repeatedly scan old large configs.
UPDATE workflow_runs SET config=config;
