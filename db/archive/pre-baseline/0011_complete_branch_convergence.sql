-- The architecture migration may already be recorded on an upgraded database.
-- Finish the alias transition without copying runs, replacing keys or resetting
-- paid sessions, approved write plans, reservations, receipts or history.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname=current_schema() AND c.relname='workflow_runs')
       AND EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname=current_schema() AND c.relname='account_runs' AND c.relkind='r') THEN
        ALTER TABLE account_runs RENAME TO workflow_runs;
        CREATE VIEW account_runs AS SELECT * FROM workflow_runs;
    END IF;
END $$;
