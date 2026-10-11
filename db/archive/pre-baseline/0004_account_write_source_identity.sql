-- Relative paths are unique only within a connected source. Two granted
-- folders may both contain records.xlsx in the same reviewed batch.
ALTER TABLE account_writes DROP CONSTRAINT account_writes_tenant_id_run_id_path_key;
ALTER TABLE account_writes ADD CONSTRAINT account_writes_run_source_path_key
    UNIQUE (tenant_id, run_id, source_id, path);
