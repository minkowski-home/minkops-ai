-- Production Database Schema (minkops_app)
-- optimized for high-concurrency, OLTP, and State Management.

DROP DATABASE IF EXISTS minkops_app;
CREATE DATABASE minkops_app;
\c minkops_app

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. TENANTS
-- The "Employers". Every piece of data must link back to this.
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,                       -- e.g. "acme_corp"
    name TEXT NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,          -- branding, specific rules, API keys
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. RUNS (The "Session" or "Job")
-- Tracks a single execution flow (e.g. processing one email).
-- A run is not a "run" in the traditional sense because the agents are desinged to be long-running and event-driven.
-- Instead, think of a "run" as a unit of atomic work for one particular trigger (e.g.replying to a new email, escalating a ticket, etc).
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    agent_id TEXT NOT NULL,                    -- e.g. "imel"
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'sleeping')),
    input_payload JSONB NOT NULL,              -- What triggered this?
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_runs_tenant ON runs(tenant_id);
CREATE INDEX idx_runs_status ON runs(status);

-- 3. AGENT STATE (Short-Term Memory)
-- This is where LangGraph checkpoints are saved.
-- It's a "Journal" of the agent's brain.
CREATE TABLE agent_state (
    run_id UUID PRIMARY KEY REFERENCES runs(id),
    checkpoint_id INT NOT NULL,                -- Monotonically increasing step number
    state_data JSONB NOT NULL,                 -- The full "ImelState" or "KallState"
    node_name TEXT NOT NULL,                   -- Which step of the graph are we at?
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. MESSAGES (Context)
-- Chat history
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES runs(id),
    tenant_id TEXT NOT NULL,
    current_role TEXT NOT NULL CHECK (current_role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_messages_run ON messages(run_id, created_at);

-- 5. EVENT OUTBOX (The "Nervous System" Output)
-- When an agent wants to "do" something (send email, call caller), 
-- it writes here. A separate worker picks it up.
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID REFERENCES runs(id),
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,                  -- e.g. "send_email", "trigger_agent"
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. AUDIT LOGS (Sync to Warehouse)
-- A flattened log table purely for Airbyte to slurp up.
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,    -- does not REFERENCE because logs are loosedly coupled - they are mainly for record keeping and dont control the flow of the app
    agent_id TEXT NOT NULL,     -- same as above
    run_id UUID,
    event TEXT NOT NULL,                       -- "processed_email", "escalated_ticket"
    summary TEXT,                              -- Human readable summary
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
-- Airbyte will do standard Incremental Sync on `created_at`
CREATE INDEX idx_logs_sync ON activity_logs(created_at);

-- 7. SEED DATA
INSERT INTO tenants (id, name, config, enabled) VALUES
('acme_corp', 'Acme Corp', '{"region": "us-east-1", "plan": "enterprise"}'::jsonb, TRUE),
('start_up_inc', 'StartUp Inc', '{"region": "us-west-2", "plan": "starter"}'::jsonb, TRUE);
