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
    -- Notice that event_type is not a check constrained value, but a free-form text.
    -- This is for extensibility - everytime a new capability gets built, a new event_types get registered
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
-- Pull-based work queue for human→agent task delegation (human instructs, agent executes).
-- Agent→human interrupts are intentionally kept in agent_intercom_queue
-- (kind='question'|'signal', channel='human_interrupts') to preserve distinct
-- semantics: who consumes, SLA model, and ack contract differ between the two lanes.
CREATE TABLE human_instructions_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES tenants(id),

    -- last run spawned for this instruction; renamed from run_id because retries
    -- can spawn multiple runs — this always points to the most recent one.
    last_run_id UUID REFERENCES runs(id),

    author_id TEXT NOT NULL,                        -- Human manager identifier (email/handle)

    -- Routing: "target" = human intent, "assigned" = planner/runtime decision.
    -- Keeping them separate supports role-based routing, load balancing, and
    -- reassignment without overwriting the original human intent.
    target_agent_id TEXT,                           -- Preferred agent (e.g. "imel")
    target_role TEXT,                               -- Preferred role group (e.g. "support")
    assigned_agent_id TEXT,                         -- Resolved agent that will execute
    assigned_by TEXT,                               -- Who made the assignment (planner agent id or "system")
    assigned_at TIMESTAMP WITH TIME ZONE,

    -- Content
    instruction TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,

    -- Scheduling / priority
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    available_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), -- earliest claimable time; used for backoff scheduling
    due_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '2 days'),

    -- Status machine:
    --   claimable   → queued
    --   claimed     → acknowledged  (lease acquired)
    --   running     → in_progress
    --   success     → completed     (terminal)
    --   non-success → dismissed, expired, dead  (terminal)
    --   retryable   → failed        (non-terminal; re-enters queued after backoff)
    --   waiting     → blocked       (non-terminal; awaiting human input, not auto-retried)
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'acknowledged', 'in_progress', 'completed',
        'failed', 'dead', 'blocked', 'dismissed', 'expired'
    )),

    -- Retry / backoff (mirrors event_outbox contract for consistency)
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,            -- intentionally lower than event_outbox (3 vs 10):
                                                    -- human-authored tasks should surface failures quickly
    last_error TEXT,

    -- Leasing: standard FOR UPDATE SKIP LOCKED pattern for safe concurrent workers.
    -- If a worker dies mid-run, another worker can reclaim once lease_expires_at passes.
    locked_at TIMESTAMP WITH TIME ZONE,
    locked_by TEXT,                                 -- worker identity, e.g. "ai-suite:hostname:pid"
    lease_expires_at TIMESTAMP WITH TIME ZONE,

    -- Lifecycle timestamps
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by TEXT,
    completed_at TIMESTAMP WITH TIME ZONE,
    completed_by TEXT,

    -- Results
    agent_response TEXT,                            -- human-readable summary for UI display
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb, -- structured output for dashboard and downstream automation

    -- RLHF training data
    human_feedback TEXT,
    feedback_score INT CHECK (feedback_score BETWEEN 1 AND 5),

    -- Idempotency: prevents duplicate agendas from UI retries or integration double-submits
    idempotency_key TEXT,

    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Primary claim query: next claimable work for a tenant, ordered by priority then age
CREATE INDEX idx_hiq_claim ON human_instructions_queue(tenant_id, status, available_at, created_at DESC);

-- Targeted claim: worker looks for explicitly assigned work first
CREATE INDEX idx_hiq_assigned ON human_instructions_queue(tenant_id, assigned_agent_id, status, available_at);

-- Targeted claim: fallback routing via original human intent
CREATE INDEX idx_hiq_target_agent ON human_instructions_queue(tenant_id, target_agent_id, status, available_at);

-- Lease expiry sweep: reclaim instructions whose worker died
CREATE INDEX idx_hiq_lease_expires ON human_instructions_queue(lease_expires_at)
WHERE lease_expires_at IS NOT NULL;

-- Expiry sweep: mark overdue instructions expired
CREATE INDEX idx_hiq_expires ON human_instructions_queue(expires_at);

-- Idempotency enforcement
CREATE UNIQUE INDEX idx_hiq_idempotency ON human_instructions_queue(tenant_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

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
