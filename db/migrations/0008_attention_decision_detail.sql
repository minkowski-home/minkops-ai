-- Structured, tenant-scoped consent evidence; summaries remain short prose.
ALTER TABLE attention_events ADD COLUMN detail jsonb NOT NULL DEFAULT '{}'
    CHECK (jsonb_typeof(detail) = 'object');
CREATE UNIQUE INDEX attention_bulk_decision_once ON attention_events
    (tenant_id, item_id, (detail->>'preview_token'), (detail->>'member_key'))
    WHERE action = 'bulk_decision';
