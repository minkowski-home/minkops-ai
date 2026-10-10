-- Final OLTP baseline. Legacy adoption is handled by migrate.py, never by rebuilding tables.
-- Keep identifiers/constraints compatible with the immutable pre-baseline archive.

CREATE FUNCTION notify_workflow_worker() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.state IS DISTINCT FROM OLD.state THEN
        UPDATE worker_wakeup SET generation=generation+1 WHERE singleton;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TABLE account_catalogs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    definition_version text NOT NULL,
    catalog jsonb NOT NULL,
    confirmed_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE account_files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    path text NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    current boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    schema_only boolean DEFAULT false NOT NULL
);

CREATE TABLE workflow_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    workflow_key text NOT NULL,
    definition_version text NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    config jsonb NOT NULL,
    file_ids jsonb NOT NULL,
    catalog_id uuid,
    state text DEFAULT 'queued'::text NOT NULL,
    session_id text,
    turn_id text,
    result jsonb,
    review_actor_id uuid,
    reviewed_at timestamp with time zone,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    parent_run_id uuid,
    CONSTRAINT account_runs_state_check CHECK ((state = ANY (ARRAY['queued'::text, 'executing'::text, 'review'::text, 'approved'::text, 'writing'::text, 'completed'::text, 'failed'::text])))
);

CREATE VIEW account_runs AS
 SELECT id,
    tenant_id,
    task_id,
    actor_id,
    workflow_key,
    definition_version,
    request_key,
    request_hash,
    config,
    file_ids,
    catalog_id,
    state,
    session_id,
    turn_id,
    result,
    review_actor_id,
    reviewed_at,
    error,
    updated_at,
    parent_run_id
   FROM workflow_runs;

CREATE TABLE account_sources (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    label text NOT NULL,
    writable boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE account_tally_writes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    device_id uuid NOT NULL,
    company text NOT NULL,
    identity text NOT NULL,
    record_index integer NOT NULL,
    plan jsonb NOT NULL,
    outcome text,
    receipt jsonb,
    verified_at timestamp with time zone,
    finished_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    destination_key text NOT NULL
);

CREATE TABLE account_writes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    file_id uuid NOT NULL,
    source_id uuid NOT NULL,
    path text NOT NULL,
    before_sha256 text NOT NULL,
    after_sha256 text NOT NULL,
    content bytea NOT NULL,
    changes jsonb NOT NULL,
    verified_at timestamp with time zone,
    cancelled_at timestamp with time zone
);

CREATE TABLE attention_events (
    id bigint NOT NULL,
    tenant_id uuid NOT NULL,
    item_id uuid NOT NULL,
    actor_id uuid,
    action text NOT NULL,
    summary text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT attention_events_summary_check CHECK ((length(summary) <= 300))
);

ALTER TABLE attention_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME attention_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE attention_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    event_key text NOT NULL,
    identifier text NOT NULL,
    label text NOT NULL,
    kind text NOT NULL,
    target jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    authorized_by uuid,
    done_by uuid,
    done_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT attention_items_label_check CHECK (((length(label) >= 1) AND (length(label) <= 80))),
    CONSTRAINT attention_items_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'done'::text])))
);

CREATE TABLE desktop_devices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    installation_id uuid NOT NULL,
    name text NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone DEFAULT (now() + '90 days'::interval) NOT NULL,
    revoked_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT desktop_devices_name_check CHECK (((length(name) >= 1) AND (length(name) <= 80)))
);

CREATE TABLE desktop_job_requests (
    tenant_id uuid NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    job_id uuid NOT NULL
);

CREATE TABLE desktop_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    task_id uuid NOT NULL,
    operation text NOT NULL,
    input jsonb DEFAULT '{}'::jsonb NOT NULL,
    state text DEFAULT 'queued'::text NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    claim_token uuid,
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    result jsonb,
    error text,
    receipt_hash text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT desktop_jobs_operation_check CHECK ((operation = ANY (ARRAY['tally.probe'::text, 'files.refresh'::text, 'accounts.save'::text, 'tally.save'::text, 'sources.discover'::text, 'tally.references'::text, 'attention.refresh'::text, 'attention.supplier'::text]))),
    CONSTRAINT desktop_jobs_state_check CHECK ((state = ANY (ARRAY['queued'::text, 'executing'::text, 'completed'::text, 'failed'::text])))
);

CREATE TABLE desktop_source_bindings (
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    source_id uuid NOT NULL
);

CREATE TABLE discovery_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    device_id uuid NOT NULL,
    task_id uuid NOT NULL,
    job_id uuid,
    mapping_run_id uuid,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    config jsonb NOT NULL,
    observations jsonb DEFAULT '[]'::jsonb NOT NULL,
    catalog jsonb,
    state text DEFAULT 'queued'::text NOT NULL,
    fingerprint text,
    confirmed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT discovery_runs_state_check CHECK ((state = ANY (ARRAY['queued'::text, 'executing'::text, 'review'::text, 'completed'::text, 'failed'::text])))
);

CREATE TABLE email_verifications (
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL
);

CREATE TABLE employees (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    key text NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    config_schema jsonb DEFAULT '{"type": "object", "properties": {}}'::jsonb NOT NULL,
    config_values jsonb DEFAULT '{}'::jsonb NOT NULL,
    config_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT employees_config_schema_check CHECK ((jsonb_typeof(config_schema) = 'object'::text)),
    CONSTRAINT employees_config_values_check CHECK ((jsonb_typeof(config_values) = 'object'::text)),
    CONSTRAINT employees_config_version_check CHECK ((config_version > 0)),
    CONSTRAINT employees_status_check CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text])))
);

CREATE TABLE event_outbox (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    event_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    published_at timestamp with time zone
);

CREATE TABLE invitations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    email text NOT NULL,
    role text NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    accepted_at timestamp with time zone,
    invited_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT invitations_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'member'::text])))
);

CREATE TABLE join_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT join_requests_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text])))
);

CREATE TABLE memberships (
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT memberships_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'member'::text])))
);

CREATE TABLE sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE task_events (
    id bigint NOT NULL,
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    event_type text NOT NULL,
    summary text NOT NULL,
    progress integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT task_events_progress_check CHECK (((progress >= 0) AND (progress <= 100)))
);

ALTER TABLE task_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME task_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    workflow_id uuid,
    title text NOT NULL,
    status text DEFAULT 'running'::text NOT NULL,
    progress integer DEFAULT 0 NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tasks_progress_check CHECK (((progress >= 0) AND (progress <= 100))),
    CONSTRAINT tasks_status_check CHECK ((status = ANY (ARRAY['running'::text, 'attention'::text, 'handoff'::text, 'completed'::text, 'failed'::text])))
);

CREATE TABLE tenant_domains (
    domain text NOT NULL,
    tenant_id uuid NOT NULL,
    verified_at timestamp with time zone,
    CONSTRAINT tenant_domains_domain_check CHECK ((domain = lower(domain)))
);

CREATE TABLE tenants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tenants_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]*$'::text))
);

CREATE TABLE users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    name text NOT NULL,
    password_hash text NOT NULL,
    email_verified_at timestamp with time zone,
    is_platform_admin boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE worker_wakeup (
    singleton boolean DEFAULT true NOT NULL,
    generation bigint DEFAULT 0 NOT NULL,
    acknowledged bigint DEFAULT 0 NOT NULL,
    lease_until timestamp with time zone,
    dispatch_token uuid,
    CONSTRAINT worker_wakeup_check CHECK ((acknowledged <= generation)),
    CONSTRAINT worker_wakeup_singleton_check CHECK (singleton)
);

CREATE TABLE workflow_employees (
    tenant_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    employee_id uuid NOT NULL
);

CREATE TABLE workflows (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    key text NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'planned'::text NOT NULL,
    config_schema jsonb DEFAULT '{"type": "object", "properties": {}}'::jsonb NOT NULL,
    config_values jsonb DEFAULT '{}'::jsonb NOT NULL,
    config_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    execution_binding jsonb,
    CONSTRAINT workflows_config_schema_check CHECK ((jsonb_typeof(config_schema) = 'object'::text)),
    CONSTRAINT workflows_config_values_check CHECK ((jsonb_typeof(config_values) = 'object'::text)),
    CONSTRAINT workflows_config_version_check CHECK ((config_version > 0)),
    CONSTRAINT workflows_execution_binding_object CHECK (((execution_binding IS NULL) OR (jsonb_typeof(execution_binding) = 'object'::text))),
    CONSTRAINT workflows_status_check CHECK ((status = ANY (ARRAY['active'::text, 'paused'::text, 'planned'::text])))
);

ALTER TABLE ONLY account_catalogs
    ADD CONSTRAINT account_catalogs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY account_catalogs
    ADD CONSTRAINT account_catalogs_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY account_files
    ADD CONSTRAINT account_files_pkey PRIMARY KEY (id);

ALTER TABLE ONLY account_files
    ADD CONSTRAINT account_files_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY account_files
    ADD CONSTRAINT account_files_tenant_id_source_id_path_sha256_key UNIQUE (tenant_id, source_id, path, sha256);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_tenant_id_request_key_key UNIQUE (tenant_id, request_key);

ALTER TABLE ONLY account_sources
    ADD CONSTRAINT account_sources_pkey PRIMARY KEY (id);

ALTER TABLE ONLY account_sources
    ADD CONSTRAINT account_sources_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY account_tally_writes
    ADD CONSTRAINT account_tally_writes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY account_tally_writes
    ADD CONSTRAINT account_tally_writes_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY account_writes
    ADD CONSTRAINT account_writes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY attention_events
    ADD CONSTRAINT attention_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY attention_items
    ADD CONSTRAINT attention_items_pkey PRIMARY KEY (id);

ALTER TABLE ONLY attention_items
    ADD CONSTRAINT attention_items_tenant_id_event_key_key UNIQUE (tenant_id, event_key);

ALTER TABLE ONLY attention_items
    ADD CONSTRAINT attention_items_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY desktop_devices
    ADD CONSTRAINT desktop_devices_pkey PRIMARY KEY (id);

ALTER TABLE ONLY desktop_devices
    ADD CONSTRAINT desktop_devices_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY desktop_devices
    ADD CONSTRAINT desktop_devices_tenant_id_owner_id_installation_id_key UNIQUE (tenant_id, owner_id, installation_id);

ALTER TABLE ONLY desktop_devices
    ADD CONSTRAINT desktop_devices_token_hash_key UNIQUE (token_hash);

ALTER TABLE ONLY desktop_job_requests
    ADD CONSTRAINT desktop_job_requests_pkey PRIMARY KEY (tenant_id, request_key);

ALTER TABLE ONLY desktop_jobs
    ADD CONSTRAINT desktop_jobs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY desktop_jobs
    ADD CONSTRAINT desktop_jobs_tenant_id_request_key_key UNIQUE (tenant_id, request_key);

ALTER TABLE ONLY desktop_jobs
    ADD CONSTRAINT desktop_jobs_tenant_identity UNIQUE (tenant_id, id);

ALTER TABLE ONLY desktop_source_bindings
    ADD CONSTRAINT desktop_source_bindings_pkey PRIMARY KEY (tenant_id, source_id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_request_key_key UNIQUE (tenant_id, request_key);

ALTER TABLE ONLY email_verifications
    ADD CONSTRAINT email_verifications_pkey PRIMARY KEY (user_id);

ALTER TABLE ONLY email_verifications
    ADD CONSTRAINT email_verifications_token_hash_key UNIQUE (token_hash);

ALTER TABLE ONLY employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);

ALTER TABLE ONLY employees
    ADD CONSTRAINT employees_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY employees
    ADD CONSTRAINT employees_tenant_id_key_key UNIQUE (tenant_id, key);

ALTER TABLE ONLY event_outbox
    ADD CONSTRAINT event_outbox_pkey PRIMARY KEY (id);

ALTER TABLE ONLY invitations
    ADD CONSTRAINT invitations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY invitations
    ADD CONSTRAINT invitations_token_hash_key UNIQUE (token_hash);

ALTER TABLE ONLY join_requests
    ADD CONSTRAINT join_requests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY join_requests
    ADD CONSTRAINT join_requests_tenant_id_user_id_key UNIQUE (tenant_id, user_id);

ALTER TABLE ONLY memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (tenant_id, user_id);

ALTER TABLE ONLY sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY sessions
    ADD CONSTRAINT sessions_token_hash_key UNIQUE (token_hash);

ALTER TABLE ONLY task_events
    ADD CONSTRAINT task_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);

ALTER TABLE ONLY tasks
    ADD CONSTRAINT tasks_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY tenant_domains
    ADD CONSTRAINT tenant_domains_pkey PRIMARY KEY (domain);

ALTER TABLE ONLY tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);

ALTER TABLE ONLY tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);

ALTER TABLE ONLY users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY worker_wakeup
    ADD CONSTRAINT worker_wakeup_pkey PRIMARY KEY (singleton);

ALTER TABLE ONLY workflow_employees
    ADD CONSTRAINT workflow_employees_pkey PRIMARY KEY (tenant_id, workflow_id, employee_id);

ALTER TABLE ONLY workflows
    ADD CONSTRAINT workflows_pkey PRIMARY KEY (id);

ALTER TABLE ONLY workflows
    ADD CONSTRAINT workflows_tenant_id_id_key UNIQUE (tenant_id, id);

ALTER TABLE ONLY workflows
    ADD CONSTRAINT workflows_tenant_id_key_key UNIQUE (tenant_id, key);

CREATE INDEX account_batch_children ON workflow_runs USING btree (tenant_id, parent_run_id) WHERE (parent_run_id IS NOT NULL);

CREATE UNIQUE INDEX account_files_current ON account_files USING btree (tenant_id, source_id, path) WHERE current;

CREATE INDEX account_runs_queue ON workflow_runs USING btree (updated_at) WHERE (state = ANY (ARRAY['queued'::text, 'executing'::text]));

CREATE UNIQUE INDEX account_tally_pending ON account_tally_writes USING btree (tenant_id, destination_key, identity) WHERE ((finished_at IS NULL) AND (cancelled_at IS NULL));

CREATE UNIQUE INDEX account_writes_pending ON account_writes USING btree (tenant_id, source_id, path) WHERE ((verified_at IS NULL) AND (cancelled_at IS NULL));

CREATE INDEX attention_pending ON attention_items USING btree (tenant_id, updated_at DESC, id) WHERE (status = 'pending'::text);

CREATE INDEX desktop_jobs_dispatch ON desktop_jobs USING btree (device_id, created_at) WHERE (state = ANY (ARRAY['queued'::text, 'executing'::text]));

CREATE INDEX discovery_recent ON discovery_runs USING btree (tenant_id, device_id, created_at DESC);

CREATE INDEX event_outbox_pending_idx ON event_outbox USING btree (created_at) WHERE (published_at IS NULL);

CREATE INDEX invitations_tenant_email_idx ON invitations USING btree (tenant_id, lower(email));

CREATE INDEX memberships_user_id_idx ON memberships USING btree (user_id);

CREATE INDEX sessions_user_id_idx ON sessions USING btree (user_id);

CREATE INDEX task_events_task_idx ON task_events USING btree (tenant_id, task_id, id);

CREATE INDEX tasks_tenant_status_idx ON tasks USING btree (tenant_id, status, updated_at DESC);

CREATE UNIQUE INDEX users_email_unique ON users USING btree (lower(email));

CREATE INDEX workflow_employees_employee_idx ON workflow_employees USING btree (tenant_id, employee_id);

CREATE INDEX workflows_tenant_status_idx ON workflows USING btree (tenant_id, status);

CREATE TRIGGER tally_context_worker_wakeup AFTER UPDATE OF state ON desktop_jobs FOR EACH ROW WHEN (((new.operation = 'tally.references'::text) AND (new.state = ANY (ARRAY['completed'::text, 'failed'::text])) AND (new.state IS DISTINCT FROM old.state))) EXECUTE FUNCTION notify_workflow_worker();

CREATE TRIGGER workflow_worker_wakeup AFTER INSERT OR UPDATE OF state ON workflow_runs FOR EACH ROW EXECUTE FUNCTION notify_workflow_worker();

ALTER TABLE ONLY account_catalogs
    ADD CONSTRAINT account_catalogs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE ONLY account_catalogs
    ADD CONSTRAINT account_catalogs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);

ALTER TABLE ONLY account_files
    ADD CONSTRAINT account_files_tenant_id_source_id_fkey FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources(tenant_id, id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_run_parent FOREIGN KEY (tenant_id, parent_run_id) REFERENCES workflow_runs(tenant_id, id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_review_actor_id_fkey FOREIGN KEY (review_actor_id) REFERENCES users(id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_tenant_id_catalog_id_fkey FOREIGN KEY (tenant_id, catalog_id) REFERENCES account_catalogs(tenant_id, id);

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT account_runs_tenant_id_task_id_fkey FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id);

ALTER TABLE ONLY account_sources
    ADD CONSTRAINT account_sources_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE ONLY account_sources
    ADD CONSTRAINT account_sources_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);

ALTER TABLE ONLY account_tally_writes
    ADD CONSTRAINT account_tally_writes_tenant_id_device_id_fkey FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id);

ALTER TABLE ONLY account_tally_writes
    ADD CONSTRAINT account_tally_writes_tenant_id_run_id_fkey FOREIGN KEY (tenant_id, run_id) REFERENCES workflow_runs(tenant_id, id);

ALTER TABLE ONLY account_writes
    ADD CONSTRAINT account_writes_tenant_id_file_id_fkey FOREIGN KEY (tenant_id, file_id) REFERENCES account_files(tenant_id, id);

ALTER TABLE ONLY account_writes
    ADD CONSTRAINT account_writes_tenant_id_run_id_fkey FOREIGN KEY (tenant_id, run_id) REFERENCES workflow_runs(tenant_id, id);

ALTER TABLE ONLY account_writes
    ADD CONSTRAINT account_writes_tenant_id_source_id_fkey FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources(tenant_id, id);

ALTER TABLE ONLY attention_events
    ADD CONSTRAINT attention_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE ONLY attention_events
    ADD CONSTRAINT attention_events_tenant_id_item_id_fkey FOREIGN KEY (tenant_id, item_id) REFERENCES attention_items(tenant_id, id);

ALTER TABLE ONLY attention_items
    ADD CONSTRAINT attention_items_authorized_by_fkey FOREIGN KEY (authorized_by) REFERENCES users(id);

ALTER TABLE ONLY attention_items
    ADD CONSTRAINT attention_items_done_by_fkey FOREIGN KEY (done_by) REFERENCES users(id);

ALTER TABLE ONLY attention_items
    ADD CONSTRAINT attention_items_tenant_id_task_id_fkey FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id);

ALTER TABLE ONLY desktop_devices
    ADD CONSTRAINT desktop_devices_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY desktop_devices
    ADD CONSTRAINT desktop_devices_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY desktop_job_requests
    ADD CONSTRAINT desktop_job_requests_tenant_id_job_id_fkey FOREIGN KEY (tenant_id, job_id) REFERENCES desktop_jobs(tenant_id, id);

ALTER TABLE ONLY desktop_jobs
    ADD CONSTRAINT desktop_jobs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE ONLY desktop_jobs
    ADD CONSTRAINT desktop_jobs_tenant_id_device_id_fkey FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id);

ALTER TABLE ONLY desktop_jobs
    ADD CONSTRAINT desktop_jobs_tenant_id_task_id_fkey FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id);

ALTER TABLE ONLY desktop_source_bindings
    ADD CONSTRAINT desktop_source_bindings_tenant_id_device_id_fkey FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id);

ALTER TABLE ONLY desktop_source_bindings
    ADD CONSTRAINT desktop_source_bindings_tenant_id_source_id_fkey FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources(tenant_id, id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_device_id_fkey FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_job_id_fkey FOREIGN KEY (tenant_id, job_id) REFERENCES desktop_jobs(tenant_id, id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_mapping_run_id_fkey FOREIGN KEY (tenant_id, mapping_run_id) REFERENCES workflow_runs(tenant_id, id);

ALTER TABLE ONLY discovery_runs
    ADD CONSTRAINT discovery_runs_tenant_id_task_id_fkey FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id);

ALTER TABLE ONLY email_verifications
    ADD CONSTRAINT email_verifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY employees
    ADD CONSTRAINT employees_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY event_outbox
    ADD CONSTRAINT event_outbox_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY invitations
    ADD CONSTRAINT invitations_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES users(id);

ALTER TABLE ONLY invitations
    ADD CONSTRAINT invitations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY join_requests
    ADD CONSTRAINT join_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY join_requests
    ADD CONSTRAINT join_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY memberships
    ADD CONSTRAINT memberships_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY task_events
    ADD CONSTRAINT task_events_tenant_id_task_id_fkey FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY tasks
    ADD CONSTRAINT tasks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY tasks
    ADD CONSTRAINT tasks_tenant_id_workflow_id_fkey FOREIGN KEY (tenant_id, workflow_id) REFERENCES workflows(tenant_id, id);

ALTER TABLE ONLY tenant_domains
    ADD CONSTRAINT tenant_domains_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE ONLY workflow_employees
    ADD CONSTRAINT workflow_employees_tenant_id_employee_id_fkey FOREIGN KEY (tenant_id, employee_id) REFERENCES employees(tenant_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY workflow_employees
    ADD CONSTRAINT workflow_employees_tenant_id_workflow_id_fkey FOREIGN KEY (tenant_id, workflow_id) REFERENCES workflows(tenant_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY workflow_runs
    ADD CONSTRAINT workflow_runs_registered_workflow FOREIGN KEY (tenant_id, workflow_key) REFERENCES workflows(tenant_id, key);

ALTER TABLE ONLY workflows
    ADD CONSTRAINT workflows_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Required runtime coordination state, not tenant/demo data.
INSERT INTO worker_wakeup (singleton) VALUES (true);
