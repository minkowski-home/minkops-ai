-- Schema projections never count as authoritative destination bytes.
ALTER TABLE account_files ADD COLUMN schema_only boolean NOT NULL DEFAULT false;
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check
 CHECK(operation IN ('tally.probe','files.refresh','accounts.save','sources.discover','tally.save','tally.references'));
