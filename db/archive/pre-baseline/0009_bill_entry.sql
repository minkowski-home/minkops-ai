-- Immutable approved financial intents. A reservation lasts until a verified
-- receipt or explicit cancellation; uncertain writes are never auto-reclaimed.
CREATE TABLE account_tally_writes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL,
 run_id uuid NOT NULL,
 device_id uuid NOT NULL,
 company text NOT NULL,
 identity text NOT NULL,
 record_index integer NOT NULL,
 plan jsonb NOT NULL,
 outcome text,
 receipt jsonb,
 verified_at timestamptz,
 finished_at timestamptz,
 cancelled_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES account_runs(tenant_id,id),
 FOREIGN KEY(tenant_id,device_id) REFERENCES desktop_devices(tenant_id,id)
);
CREATE UNIQUE INDEX account_tally_pending ON account_tally_writes(tenant_id,device_id,company,identity)
 WHERE finished_at IS NULL AND cancelled_at IS NULL;
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check
 CHECK(operation IN ('tally.probe','files.refresh','accounts.save','sources.discover','tally.save'));
ALTER TABLE account_runs ADD COLUMN parent_run_id uuid;
ALTER TABLE account_runs ADD CONSTRAINT account_run_parent
 FOREIGN KEY(tenant_id,parent_run_id) REFERENCES account_runs(tenant_id,id);
CREATE INDEX account_batch_children ON account_runs(tenant_id,parent_run_id) WHERE parent_run_id IS NOT NULL;
-- A held bill may be approved later in the same run, after earlier writes were
-- verified. Keep every revision; the pending reservation still serializes saves.
ALTER TABLE account_writes DROP CONSTRAINT account_writes_run_source_path_key;
