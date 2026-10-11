-- Runs before the two immutable 0009 branch migrations on a fresh install.
-- On an architecture-first database, temporarily restore the legacy table name
-- so Bill Entry's original foreign keys/ALTER TABLE operate on that same OID.
-- The migrator applies all pending files in one transaction; no intermediate
-- table name is exposed to application connections. 0011 restores the shared
-- table/view names, including Bill Entry's newly added parent column.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=current_schema() AND c.relname='account_runs' AND c.relkind='v')
       AND EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname=current_schema() AND c.relname='workflow_runs' AND c.relkind='r') THEN
        DROP VIEW account_runs;
        ALTER TABLE workflow_runs RENAME TO account_runs;
    END IF;
END $$;
