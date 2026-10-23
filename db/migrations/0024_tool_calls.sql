-- Every function-tool call a session makes, and the answer it was given. The
-- answer is stored as sent, so a lane that restarts re-sends the identical
-- answer instead of recomputing it; calls are audit evidence of what the model
-- looked up and proposed.
CREATE TABLE tool_calls (
    tenant_id uuid NOT NULL,
    item_id uuid NOT NULL,
    session_id text NOT NULL,
    call_id text NOT NULL,
    turn_id text NOT NULL,
    name text NOT NULL CHECK (name ~ '^[a-z][a-z0-9_]{0,63}$'),
    arguments jsonb NOT NULL,
    success boolean NOT NULL,
    -- The text sent back: the JSON result, or a short reason the model can act on.
    answer text NOT NULL CHECK (length(answer) <= 65536),
    duration_ms integer NOT NULL CHECK (duration_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, call_id),
    FOREIGN KEY (tenant_id, item_id) REFERENCES run_items(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX tool_calls_item ON tool_calls (item_id, created_at);
