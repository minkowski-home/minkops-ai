-- Creating a session is not idempotent at the provider. An item records when
-- it asked for one, so a lane that takes it over without a saved session ID
-- first looks for that session by its metadata instead of starting another.
ALTER TABLE run_items ADD COLUMN session_requested_at timestamptz;

-- Finished items whose provider session is still open. A worker records each
-- turn's usage once the provider reports it (seconds after the turn ends),
-- then deletes the session; a restarted worker carries on with the same rows.
CREATE INDEX run_items_unclosed ON run_items (finished_at)
    WHERE session_id IS NOT NULL AND NOT session_closed AND state IN ('done', 'failed', 'cancelled');
