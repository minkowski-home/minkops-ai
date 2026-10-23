-- A run's files upload in batches under the per-request limit. An upload opens
-- a new source and stages each batch's files without making them current; its
-- final batch checks the whole set and makes it current in one transaction, so
-- an abandoned upload leaves nothing current. A day-old upload never finished
-- is removed with its source and staged files, which no run can have read.
CREATE TABLE account_uploads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    source_id uuid NOT NULL,
    actor_id uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    committed_at timestamptz,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, source_id),
    FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX account_uploads_open ON account_uploads (tenant_id, created_at) WHERE committed_at IS NULL;
ALTER TABLE account_files ADD COLUMN upload_id uuid;
ALTER TABLE account_files ADD CONSTRAINT account_files_upload_fkey FOREIGN KEY (tenant_id, upload_id)
    REFERENCES account_uploads(tenant_id, id) ON DELETE CASCADE;
CREATE INDEX account_files_upload ON account_files (upload_id) WHERE upload_id IS NOT NULL;
