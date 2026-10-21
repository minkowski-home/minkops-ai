-- A response can be lost after commit. A member's exact decision can be read
-- and replayed without repeating its audit, dependency release or paid work.
CREATE TABLE attention_decision_receipts (
    tenant_id uuid NOT NULL,
    item_id uuid NOT NULL,
    actor_id uuid NOT NULL REFERENCES users(id),
    action text NOT NULL,
    status text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,item_id,actor_id),
    FOREIGN KEY (tenant_id,item_id) REFERENCES attention_items(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX task_events_latest_stage ON task_events(tenant_id,task_id,id DESC)
    WHERE event_type NOT LIKE 'control.%';
