-- A supplier ledger a person approved for a bill is created by the companion
-- as its own native write, in the same per-PC order as voucher saves.
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK (operation = ANY (ARRAY[
    'tally.probe', 'files.refresh', 'accounts.save', 'tally.save', 'sources.discover', 'tally.references',
    'attention.refresh', 'attention.supplier', 'tally.statement', 'tally.sync', 'tally.write', 'tally.supplier']));
