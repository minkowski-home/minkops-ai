-- Immutable file versions pin the evidence used by discovery and bill runs.
-- Browser directory handles remain local; the server stores only granted files.
CREATE TABLE account_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    actor_id uuid NOT NULL REFERENCES users(id),
    label text NOT NULL,
    writable boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);
CREATE TABLE account_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    path text NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    current boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, source_id, path, sha256),
    FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources (tenant_id, id)
);
CREATE UNIQUE INDEX account_files_current ON account_files (tenant_id, source_id, path) WHERE current;
CREATE TABLE account_catalogs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    actor_id uuid NOT NULL REFERENCES users(id),
    definition_version text NOT NULL,
    catalog jsonb NOT NULL,
    confirmed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);
CREATE TABLE account_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    actor_id uuid NOT NULL REFERENCES users(id),
    workflow_key text NOT NULL CHECK (workflow_key IN ('source-discovery', 'bill-entry')),
    definition_version text NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    config jsonb NOT NULL,
    file_ids jsonb NOT NULL,
    catalog_id uuid,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN
        ('queued', 'executing', 'review', 'approved', 'writing', 'completed', 'failed')),
    session_id text,
    turn_id text,
    result jsonb,
    review_actor_id uuid REFERENCES users(id),
    reviewed_at timestamptz,
    error text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, request_key),
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id),
    FOREIGN KEY (tenant_id, catalog_id) REFERENCES account_catalogs (tenant_id, id)
);
CREATE INDEX account_runs_queue ON account_runs (updated_at) WHERE state IN ('queued', 'executing');
CREATE TABLE account_writes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    file_id uuid NOT NULL,
    source_id uuid NOT NULL,
    path text NOT NULL,
    before_sha256 text NOT NULL,
    after_sha256 text NOT NULL,
    content bytea NOT NULL,
    changes jsonb NOT NULL,
    verified_at timestamptz,
    UNIQUE (tenant_id, run_id, path),
    FOREIGN KEY (tenant_id, run_id) REFERENCES account_runs (tenant_id, id),
    FOREIGN KEY (tenant_id, file_id) REFERENCES account_files (tenant_id, id),
    FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources (tenant_id, id)
);
-- One outstanding local write per workbook prevents two approvals racing to
-- overwrite the same original. Other sources and tenants remain independent.
CREATE UNIQUE INDEX account_writes_pending ON account_writes (tenant_id, source_id, path)
    WHERE verified_at IS NULL;
