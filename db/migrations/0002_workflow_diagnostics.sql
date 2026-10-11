-- Internal support evidence is separate from customer-visible task events.
CREATE TABLE workflow_run_diagnostics (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    event_type text NOT NULL,
    level text NOT NULL CHECK (level IN ('info', 'warning', 'error')),
    summary text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (tenant_id, run_id) REFERENCES workflow_runs(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX workflow_run_diagnostics_run_idx
    ON workflow_run_diagnostics(tenant_id, run_id, id);
