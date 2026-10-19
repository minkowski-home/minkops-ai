-- Add only a fixed Payment/Receipt contract. Existing native plans remain pinned.
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK (operation IN
 ('tally.probe','files.refresh','accounts.save','tally.save','sources.discover','tally.references','attention.refresh','attention.supplier','tally.statement'));
