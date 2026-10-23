-- Every provider session an item opened: one per attempt, with the usage the
-- provider reported for its turn. A retry or a recheck opens another session,
-- so a run's spend is the sum of all of them; an item kept only its latest.
CREATE TABLE item_sessions (
    tenant_id uuid NOT NULL,
    item_id uuid NOT NULL,
    session_id text NOT NULL,
    attempt integer NOT NULL CHECK (attempt >= 1),
    turn_id text,
    opened_at timestamptz NOT NULL DEFAULT now(),
    -- When its turn ended; the worker then records its usage and deletes it at the provider.
    finished_at timestamptz,
    closed boolean NOT NULL DEFAULT false,
    usage jsonb CHECK (usage IS NULL OR jsonb_typeof(usage) = 'object'),
    PRIMARY KEY (item_id, session_id),
    FOREIGN KEY (tenant_id, item_id) REFERENCES run_items(tenant_id, id) ON DELETE CASCADE
);
-- Ended sessions still open at the provider, for the worker that closes them.
CREATE INDEX item_sessions_open ON item_sessions (finished_at) WHERE finished_at IS NOT NULL AND NOT closed;

INSERT INTO item_sessions (tenant_id, item_id, session_id, attempt, turn_id, opened_at, finished_at, closed, usage)
SELECT tenant_id, id, session_id, greatest(attempt, 1), turn_id, coalesce(started_at, updated_at),
       CASE WHEN state IN ('done', 'failed', 'cancelled') THEN finished_at END, session_closed, usage
FROM run_items WHERE session_id IS NOT NULL;

DROP INDEX run_items_unclosed;
ALTER TABLE run_items DROP COLUMN usage, DROP COLUMN session_closed;
