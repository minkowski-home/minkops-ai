-- Desktop credentials grant only bounded operations for one user/workspace.
CREATE TABLE desktop_devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    installation_id uuid NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL DEFAULT now() + interval '90 days',
    revoked_at timestamptz,
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, owner_id, installation_id)
);

CREATE TABLE desktop_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    actor_id uuid NOT NULL REFERENCES users(id),
    task_id uuid NOT NULL,
    operation text NOT NULL CHECK (operation IN ('tally.probe')),
    input jsonb NOT NULL DEFAULT '{}',
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','executing','completed','failed')),
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    claim_token uuid,
    lease_until timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    result jsonb,
    error text,
    receipt_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, request_key),
    FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id)
);
CREATE INDEX desktop_jobs_dispatch ON desktop_jobs(device_id, created_at)
    WHERE state IN ('queued', 'executing');
