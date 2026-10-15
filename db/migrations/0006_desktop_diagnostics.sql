-- Support evidence sent by a connected PC: on request (Send diagnostics) or
-- attached to a Tally job receipt. Technical state only, never bill contents;
-- rows older than 30 days are removed whenever a new one is stored.
CREATE TABLE desktop_diagnostics (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    job_id uuid REFERENCES desktop_jobs(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('requested', 'job')),
    reference text NOT NULL UNIQUE CHECK (reference ~ '^D-[0-9A-Z]{6}$'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX desktop_diagnostics_created_idx ON desktop_diagnostics(created_at);
CREATE INDEX desktop_diagnostics_device_idx ON desktop_diagnostics(tenant_id, device_id, created_at DESC);
