-- Approved native vouchers of runs: one durable intent per write attempt. A
-- pending intent reserves its destination identity, so no second run writes
-- the same bank transaction or bill until this one is verified or released.
-- The companion writes one at a time per PC, in the order they were approved.
CREATE TABLE native_writes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    record_id uuid NOT NULL,
    device_id uuid NOT NULL,
    company_id uuid NOT NULL,
    destination_key text NOT NULL,
    identity text NOT NULL,
    plan jsonb NOT NULL,
    outcome text CHECK (outcome IN ('saved', 'duplicate', 'held', 'cancelled')),
    receipt jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (tenant_id, id),
    CHECK ((outcome IS NULL) = (finished_at IS NULL)),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs(tenant_id, id),
    FOREIGN KEY (tenant_id, record_id) REFERENCES run_records(tenant_id, id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id),
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id)
);
CREATE UNIQUE INDEX native_writes_pending ON native_writes (tenant_id, destination_key, identity)
    WHERE finished_at IS NULL;
CREATE INDEX native_writes_queue ON native_writes (device_id, created_at) WHERE finished_at IS NULL;
CREATE INDEX native_writes_record ON native_writes (record_id, created_at DESC);

ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK (operation = ANY (ARRAY[
    'tally.probe', 'files.refresh', 'accounts.save', 'tally.save', 'sources.discover', 'tally.references',
    'attention.refresh', 'attention.supplier', 'tally.statement', 'tally.sync', 'tally.write']));
