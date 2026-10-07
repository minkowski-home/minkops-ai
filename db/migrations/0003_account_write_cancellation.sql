-- Release an abandoned local-write reservation while retaining its audit trail.
ALTER TABLE account_writes ADD COLUMN cancelled_at timestamptz;
DROP INDEX account_writes_pending;
CREATE UNIQUE INDEX account_writes_pending ON account_writes (tenant_id, source_id, path)
    WHERE verified_at IS NULL AND cancelled_at IS NULL;
