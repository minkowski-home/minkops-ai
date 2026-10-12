-- Control intent is independent of execution facts: late verified receipts
-- remain truthful without resuming a paused or stopped task.
ALTER TABLE tasks ADD COLUMN control_state text NOT NULL DEFAULT 'active'
    CHECK (control_state IN ('active','paused','stopped'));
