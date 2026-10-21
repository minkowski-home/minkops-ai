-- A record can exist before its proposal: a statement row is known at launch,
-- and routed only when its chunk's session runs. It waits as `pending`.
ALTER TABLE run_records DROP CONSTRAINT run_records_status_check;
ALTER TABLE run_records ADD CONSTRAINT run_records_status_check CHECK (status IN
    ('pending', 'proposed', 'held', 'approved', 'writing', 'saved', 'duplicate', 'deferred'));
ALTER TABLE run_records ALTER COLUMN status SET DEFAULT 'pending';
