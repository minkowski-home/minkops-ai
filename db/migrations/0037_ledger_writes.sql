-- Create this ledger writes a general party ledger in Tally's terms (plan
-- protocol 8): a bill's new supplier, or the other side of a bank row, under
-- the group, bill-by-bill setting, credit period, mailing and GST details a
-- person approved. Its job is `tally.ledger`, replacing `tally.supplier`.
-- A supplier plan still pending would never be executed by the new
-- companion, so the upgrade waits for it to finish or be withdrawn.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM native_writes WHERE finished_at IS NULL AND plan->>'kind' = 'supplier') THEN
        RAISE EXCEPTION 'A supplier creation is still pending. Let it finish, or stop its run, before upgrading.';
    END IF;
END $$;
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
UPDATE desktop_jobs SET operation='tally.ledger' WHERE operation='tally.supplier';
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK (operation = ANY (ARRAY[
    'tally.probe', 'files.refresh', 'accounts.save', 'tally.save', 'sources.discover', 'tally.references',
    'attention.refresh', 'attention.supplier', 'tally.statement', 'tally.sync', 'tally.write', 'tally.ledger']));
