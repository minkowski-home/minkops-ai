-- Compute is reused only within one operator's batch, after session cleanup.
CREATE TABLE hosted_environment_slots (
    tenant_id uuid NOT NULL,
    group_run_id uuid NOT NULL,
    slot smallint NOT NULL CHECK (slot BETWEEN 0 AND 3),
    profile_hash text NOT NULL,
    environment_id text,
    attachments smallint NOT NULL DEFAULT 0 CHECK (attachments BETWEEN 0 AND 128),
    busy_run_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, group_run_id, slot),
    FOREIGN KEY (tenant_id, group_run_id) REFERENCES workflow_runs(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, busy_run_id) REFERENCES workflow_runs(tenant_id, id)
);
