-- The rebuild's run model: one session per bill or statement chunk, with
-- scheduling state in columns, never in run JSON, and no evidence copied in.

-- Pinned procedure (instructions, tool contracts, model settings), stored once
-- per tenant and content digest and referenced by every run that uses it.
CREATE TABLE run_bundles (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, digest)
);

CREATE TABLE runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    client_id uuid NOT NULL,
    task_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    workflow_key text NOT NULL,
    -- Pinned from the installed definition at launch; never from a request.
    handler text NOT NULL CHECK (handler ~ '^[a-z][a-z0-9.-]{0,40}$'),
    definition_version text NOT NULL,
    bundle_digest text NOT NULL,
    actor_id uuid NOT NULL REFERENCES users(id),
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    -- Small by contract: selections and policy, never evidence or snapshots.
    config jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(config) = 'object' AND pg_column_size(config) <= 16384),
    -- {company_id: mirror version}; set when the run is ready and never moved.
    pins jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pins) = 'object'),
    state text NOT NULL DEFAULT 'preparing'
        CHECK (state IN ('preparing', 'running', 'review', 'writing', 'completed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, request_key),
    FOREIGN KEY (tenant_id, client_id) REFERENCES client_businesses(tenant_id, id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id),
    FOREIGN KEY (tenant_id, workflow_id) REFERENCES workflows(tenant_id, id),
    FOREIGN KEY (tenant_id, bundle_digest) REFERENCES run_bundles(tenant_id, digest)
);
CREATE INDEX runs_client ON runs (tenant_id, client_id, created_at DESC);

-- The scheduling unit: one bill, one statement chunk or one layout reading.
-- A lease fences each attempt; a saved provider session is reattached, never
-- recreated, by whichever lane next holds the lease.
CREATE TABLE run_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    kind text NOT NULL CHECK (kind ~ '^[a-z][a-z_]{0,30}$'),
    source jsonb NOT NULL CHECK (jsonb_typeof(source) = 'object' AND pg_column_size(source) <= 4096),
    -- Scheduling only; what a bill or row needs is its record's status.
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('waiting', 'queued', 'running', 'done', 'failed', 'cancelled')),
    waiting_on jsonb CHECK (waiting_on IS NULL OR jsonb_typeof(waiting_on) = 'object'),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    lease_token uuid,
    lease_until timestamptz,
    session_id text,
    turn_id text,
    session_closed boolean NOT NULL DEFAULT false,
    usage jsonb,
    error_code text,
    error text CHECK (length(error) <= 400),
    queued_at timestamptz,
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (run_id, ordinal),
    CHECK ((state = 'waiting') = (waiting_on IS NOT NULL)),
    CHECK (state <> 'running' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL)),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id)
);
CREATE INDEX run_items_queued ON run_items (queued_at, id) WHERE state = 'queued';
CREATE INDEX run_items_leases ON run_items (lease_until) WHERE state = 'running';
CREATE INDEX run_items_waiting ON run_items USING gin (waiting_on jsonb_path_ops) WHERE state = 'waiting';
CREATE INDEX run_items_run ON run_items (run_id, state);

-- The review unit: one bill or one statement row. Each change bumps version;
-- a decision names the version it was taken on.
CREATE TABLE run_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    item_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    kind text NOT NULL CHECK (kind ~ '^[a-z][a-z_]{0,30}$'),
    source jsonb NOT NULL CHECK (jsonb_typeof(source) = 'object' AND pg_column_size(source) <= 4096),
    company_id uuid,
    facts jsonb,
    proposal jsonb,
    checks jsonb,
    -- Do nothing defers a record; it never writes and stays identifiable.
    status text NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'held', 'approved', 'writing', 'saved', 'duplicate', 'deferred')),
    hold_codes text[] NOT NULL DEFAULT '{}',
    review_reasons text[] NOT NULL DEFAULT '{}',
    plan jsonb,
    current jsonb,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (item_id, position),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, item_id) REFERENCES run_items(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id)
);
CREATE INDEX run_records_run ON run_records (run_id, status);

-- One decision per record version. Replaying the same actor's action returns
-- its receipt; anything else conflicts and is answered with the receipt that won.
CREATE TABLE record_decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    record_id uuid NOT NULL,
    record_version integer NOT NULL,
    actor_id uuid NOT NULL REFERENCES users(id),
    action text NOT NULL CHECK (action ~ '^[a-z][a-z_]{0,30}$'),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detail) = 'object'),
    receipt jsonb NOT NULL CHECK (jsonb_typeof(receipt) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, record_id, record_version),
    FOREIGN KEY (tenant_id, record_id) REFERENCES run_records(tenant_id, id) ON DELETE CASCADE
);

-- Wake-ups come from committed state changes: queuing an item, including
-- releasing one that waited on a decision, bumps the durable generation and
-- notifies listening workers when the transaction commits.
CREATE FUNCTION run_item_queued() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE worker_wakeup SET generation = generation + 1 WHERE singleton;
    PERFORM pg_notify('minkops_work', NEW.kind);
    RETURN NULL;
END $$;
CREATE TRIGGER run_items_inserted_queued AFTER INSERT ON run_items
    FOR EACH ROW WHEN (NEW.state = 'queued') EXECUTE FUNCTION run_item_queued();
CREATE TRIGGER run_items_became_queued AFTER UPDATE OF state ON run_items
    FOR EACH ROW WHEN (NEW.state = 'queued' AND OLD.state IS DISTINCT FROM 'queued') EXECUTE FUNCTION run_item_queued();

-- The shared active-processing budget also counts running items.
CREATE OR REPLACE FUNCTION refresh_task_processing_clock(scope uuid, task_key uuid) RETURNS void LANGUAGE plpgsql AS $$
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
        OR EXISTS (SELECT 1 FROM desktop_jobs WHERE tenant_id=scope AND task_id=task_key AND state='executing')
        OR EXISTS (SELECT 1 FROM run_items WHERE tenant_id=scope AND task_id=task_key AND state='running'));
    IF working AND current_task.processing_started_at IS NULL THEN
        UPDATE tasks SET processing_started_at=instant WHERE id=task_key;
    ELSIF NOT working AND current_task.processing_started_at IS NOT NULL THEN
        UPDATE tasks SET processing_seconds=processing_seconds+greatest(0,extract(epoch FROM instant-processing_started_at)),
            processing_started_at=NULL WHERE id=task_key;
    END IF;
END $$;
-- Items are never inserted running, so only entering or leaving it matters.
CREATE TRIGGER run_item_processing_clock AFTER UPDATE OF state ON run_items
    FOR EACH ROW WHEN (OLD.state IS DISTINCT FROM NEW.state AND 'running' IN (OLD.state, NEW.state))
    EXECUTE FUNCTION task_processing_clock_changed();
