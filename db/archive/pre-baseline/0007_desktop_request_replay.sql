-- Several browser requests can join one pending native operation. Retain each
-- key so retries still return that job after it finishes or is interrupted.
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_tenant_identity UNIQUE(tenant_id,id);
CREATE TABLE desktop_job_requests (
    tenant_id uuid NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    job_id uuid NOT NULL,
    PRIMARY KEY (tenant_id,request_key),
    FOREIGN KEY (tenant_id,job_id) REFERENCES desktop_jobs(tenant_id,id)
);
INSERT INTO desktop_job_requests(tenant_id,request_key,request_hash,job_id)
    SELECT tenant_id,request_key,request_hash,id FROM desktop_jobs;
