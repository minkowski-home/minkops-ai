-- db/schema.sql
--
-- Repeatable schema reset. Run via `seed-db` during development:
--
--   seed-db [--sql-path db/schema.sql]
--
-- Assumes `minkops_app` already exists (run db/bootstrap.sql first if starting fresh).
-- Connects directly to minkops_app — no CREATE DATABASE or \c here.

-- Production Database Schema (minkops_app)
-- Optimized for high-concurrency, OLTP, and state management.

-- ─── Teardown (reverse FK dependency order) ───────────────────────────────────
DROP TABLE IF EXISTS tenant_kb_chunks;
DROP TABLE IF EXISTS activity_logs;
DROP TABLE IF EXISTS agent_intercom_queue;
DROP TABLE IF EXISTS human_instructions_queue;
DROP TABLE IF EXISTS event_outbox;
DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS agent_state;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS tenants;

-- ─── 1. TENANTS ───────────────────────────────────────────────────────────────
-- The "Employers". Every piece of data must link back to this.
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,                       -- e.g. "acme_corp"
    name TEXT NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,          -- specific rules, API keys
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─── 2. RUNS (The "Session" or "Job") ─────────────────────────────────────────
-- Tracks a single execution flow (e.g. processing one email).
-- A run is not a "run" in the traditional sense because the agents are designed to be long-running and event-driven.
-- Instead, think of a "run" as a unit of atomic work for one particular trigger (e.g. replying to a new email, escalating a ticket, etc).
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    agent_id TEXT NOT NULL,                    -- e.g. "imel"
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'sleeping')),
    input_payload JSONB NOT NULL,              -- What triggered this?
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_runs_tenant ON runs(tenant_id); -- filter by tenant_id first because in a multi-tenant system, no tenant should ever see another tenant's data
CREATE INDEX idx_runs_status ON runs(status); -- this might be replaced by the following partial index in production
-- CREATE INDEX ON runs(tenant_id, status) WHERE status IN ('queued', 'running') -- since completed and failed runs are rarely queried.

-- ─── 3. AGENT STATE (Short-Term Memory) ───────────────────────────────────────
-- This is where LangGraph checkpoints are saved.
-- It's a "Journal" of the agent's brain.
CREATE TABLE agent_state (
    run_id UUID PRIMARY KEY REFERENCES runs(id),
    checkpoint_id INT NOT NULL,                -- Monotonically increasing step number
    state_data JSONB NOT NULL,                 -- The full "ImelState" or "KallState"
    node_name TEXT NOT NULL,                   -- Which step of the graph are we at?
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─── 4. MESSAGES (Context) ────────────────────────────────────────────────────
-- Chat history
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES runs(id),
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_messages_run ON messages(run_id, created_at);

-- ─── 4.5 TICKETS (Support Cases) ──────────────────────────────────────────────
-- Persisted tickets for human or agent follow-up.
CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    email_id TEXT NOT NULL,                    -- Link to source email
    ticket_type TEXT NOT NULL,                 -- e.g. "cancel_order", "complaint"
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority TEXT NOT NULL DEFAULT 'normal',
    sender_email TEXT NOT NULL,
    summary TEXT,
    raw_email TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_tickets_tenant_status ON tickets(tenant_id, status);
CREATE INDEX idx_tickets_email_id ON tickets(email_id);

-- ─── 5. EVENT OUTBOX (External Side Effects) ──────────────────────────────────
-- For durable, idempotent delivery of side effects to external systems.
-- Examples: send_email, create_ticket, sync_crm, trigger_webhook.
-- The Transactional Outbox pattern means the "work" (e.g., updating a customer's moodboard status in the projects table)
-- and the "instruction" (e.g., an entry in the outbox table saying "Notify the Social Media Agent")
-- happen inside the exact same database transaction.
-- The goal is to ensure that side effects happen atomically with the rest of the transaction.
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID REFERENCES runs(id),
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,                  -- e.g. "send_email", "sync_crm"
    payload JSONB NOT NULL,
    idempotency_key TEXT,                      -- Optional dedupe key per tenant/event
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'processing', 'succeeded', 'failed', 'dead'
    )),
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT,
    available_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    locked_at TIMESTAMP WITH TIME ZONE,
    locked_by TEXT,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_event_outbox_tenant_status ON event_outbox(tenant_id, status, available_at);
CREATE INDEX idx_event_outbox_available ON event_outbox(available_at);
CREATE UNIQUE INDEX idx_event_outbox_idempotency ON event_outbox(tenant_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

-- ─── 6. AUDIT LOGS (Sync to Warehouse) ────────────────────────────────────────
-- A flattened log table purely for Airbyte to slurp up.
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,    -- does not REFERENCE because logs are loosely coupled - they are mainly for record keeping and dont control the flow of the app
    agent_id TEXT NOT NULL,     -- same as above
    run_id UUID,
    event TEXT NOT NULL,                       -- "processed_email", "escalated_ticket"
    summary TEXT,                              -- Human readable summary
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
-- Airbyte will do standard Incremental Sync on `created_at`
CREATE INDEX idx_logs_sync ON activity_logs(created_at);

-- ─── 7. HUMAN INSTRUCTIONS QUEUE ──────────────────────────────────────────────
-- For human managers to instruct daily tasks, instructions, goals for the day/week, and agents to request human help asynchronously.
CREATE TABLE human_instructions_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    run_id UUID REFERENCES runs(id),
    author_id TEXT NOT NULL,                  -- Human manager identifier (email/handle)
    target_agent_id TEXT,                     -- Optional specific agent target (e.g. "imel")
    target_role TEXT,                         -- Optional group target (e.g. "support")
    instruction TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'acknowledged', 'in_progress', 'completed', 'blocked', 'dismissed', 'expired'
    )),
    due_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '2 days'),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by TEXT,
    completed_at TIMESTAMP WITH TIME ZONE,
    completed_by TEXT,
    agent_response TEXT,
    human_feedback TEXT,                      -- Capture human feedback for RLHF training data
    feedback_score INT CHECK (feedback_score BETWEEN 1 AND 5),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_hiq_tenant_status ON human_instructions_queue(tenant_id, status, created_at DESC);
CREATE INDEX idx_hiq_target_agent ON human_instructions_queue(tenant_id, target_agent_id, status);
CREATE INDEX idx_hiq_expires ON human_instructions_queue(expires_at);

-- ─── 8. AGENT INTER-COMMUNICATIONS QUEUE (Internal Messaging) ─────────────────
-- For multi-agent coordination only; no external side effects.
CREATE TABLE agent_intercom_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    run_id UUID REFERENCES runs(id),
    from_agent_id TEXT NOT NULL,
    to_agent_id TEXT,                         -- Null implies broadcast within tenant/channel
    channel TEXT,                             -- Optional topic/channel for routing
    kind TEXT NOT NULL DEFAULT 'message' CHECK (kind IN (
        'message', 'instruction', 'question', 'thought', 'handoff', 'signal'
    )),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'delivered', 'consumed', 'archived', 'failed', 'expired'
    )),
    message TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    reply_to UUID REFERENCES agent_intercom_queue(id),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '2 days'),
    delivered_at TIMESTAMP WITH TIME ZONE,
    consumed_at TIMESTAMP WITH TIME ZONE,
    consumed_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_aiq_tenant_status ON agent_intercom_queue(tenant_id, status, created_at DESC);
CREATE INDEX idx_aiq_recipient ON agent_intercom_queue(tenant_id, to_agent_id, status);
CREATE INDEX idx_aiq_channel ON agent_intercom_queue(tenant_id, channel, created_at DESC);
CREATE INDEX idx_aiq_expires ON agent_intercom_queue(expires_at);

-- ─── 9. TENANT KB CHUNKS (Vector Store) ───────────────────────────────────────
-- Stores company knowledge per tenant. If `vector` is unavailable in local
-- dev, we keep the same table contract with a JSONB embedding fallback.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
       -- Use EXECUTE because it defers the SQL validation to run-time rather than compile time.
       -- If pg_vector is absent, the compile-time validation would fail due to the presence of vector() column,
       -- so this IF statement would never execute. We don't want that.
        EXECUTE $vector_table$
            CREATE TABLE tenant_kb_chunks (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                doc_id TEXT NOT NULL,                         -- Stable identifier per source document
                source_uri TEXT,                              -- e.g., path in data/, S3 URI
                source_type TEXT NOT NULL CHECK (source_type IN (
                    'file', 'manual_entry', 'brand_kit', 'faq', 'policy', 'run_note', 'other'
                )),
                chunk_index INT NOT NULL,                     -- Chunk order within a doc
                content TEXT NOT NULL,
                embedding vector(1536) NOT NULL,              -- pgvector column for similarity search
                metadata JSONB DEFAULT '{}'::jsonb,           -- Arbitrary ingest metadata (checksum, mime_type, tags, etc.)
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        $vector_table$;
    ELSE
        EXECUTE $json_table$
            CREATE TABLE tenant_kb_chunks (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                doc_id TEXT NOT NULL,                         -- Stable identifier per source document
                source_uri TEXT,                              -- e.g., path in data/, S3 URI
                source_type TEXT NOT NULL CHECK (source_type IN (
                    'file', 'manual_entry', 'brand_kit', 'faq', 'policy', 'run_note', 'other'
                )),
                chunk_index INT NOT NULL,                     -- Chunk order within a doc
                content TEXT NOT NULL,
                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb, -- Local dev fallback without pgvector
                metadata JSONB DEFAULT '{}'::jsonb,           -- Arbitrary ingest metadata (checksum, mime_type, tags, etc.)
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        $json_table$;
    END IF;

    EXECUTE 'CREATE INDEX idx_kb_chunks_tenant_doc ON tenant_kb_chunks(tenant_id, doc_id)';
    EXECUTE 'CREATE INDEX idx_kb_chunks_tenant_source ON tenant_kb_chunks(tenant_id, source_type)';

    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        -- Cosine distance is commonly used for normalized embeddings (e.g., OpenAI).
        EXECUTE 'CREATE INDEX idx_kb_chunks_embedding ON tenant_kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
    END IF;
END $$;

-- ─── 10. SEED DATA (remove later) ─────────────────────────────────────────────
INSERT INTO tenants (id, name, config, enabled) VALUES
('acme_corp', 'Acme Corp', '{"region": "us-east-1", "plan": "enterprise"}'::jsonb, TRUE),
('start_up_inc', 'StartUp Inc', '{"region": "us-west-2", "plan": "starter"}'::jsonb, TRUE);
