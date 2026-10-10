ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check
 CHECK(operation IN ('tally.probe','files.refresh','accounts.save','sources.discover'));

CREATE TABLE discovery_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES tenants(id),
 actor_id uuid NOT NULL REFERENCES users(id),
 device_id uuid NOT NULL,
 task_id uuid NOT NULL,
 job_id uuid,
 mapping_run_id uuid,
 request_key uuid NOT NULL,
 request_hash text NOT NULL,
 config jsonb NOT NULL,
 observations jsonb NOT NULL DEFAULT '[]',
 catalog jsonb,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','executing','review','completed','failed')),
 fingerprint text,
 confirmed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,id), UNIQUE(tenant_id,request_key),
 FOREIGN KEY(tenant_id,device_id) REFERENCES desktop_devices(tenant_id,id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES tasks(tenant_id,id),
 FOREIGN KEY(tenant_id,job_id) REFERENCES desktop_jobs(tenant_id,id),
 FOREIGN KEY(tenant_id,mapping_run_id) REFERENCES account_runs(tenant_id,id)
);
CREATE INDEX discovery_recent ON discovery_runs(tenant_id,device_id,created_at DESC);
