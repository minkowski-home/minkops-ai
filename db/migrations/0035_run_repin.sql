-- Recheck reads the books afresh. A run pins one mirror version per company
-- when its first session starts, so a ledger created in Tally after that was
-- never seen by a recheck. A recheck now asks the PC holding the company to
-- refresh and lists the company here; the run's next session pins that
-- company's newly published copy once the refresh is done, and clears it.
-- The old pin stays in force until then, so a decision made meanwhile reads
-- the same books as the proposal it decides.
ALTER TABLE runs ADD COLUMN repin uuid[] NOT NULL DEFAULT '{}';
