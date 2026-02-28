-- Additional analytics-heavy practice dataset for Minkops.
-- Safe usage pattern:
--   1) Run db/bootstrap.sql + seed-db (schema.sql) first.
--   2) Run this file to add advanced SQL practice tables + data.
--
-- This script does NOT alter existing tables or db/schema.sql.
-- It only creates new tables and inserts synthetic, coherent metrics data.
-- It is supposed to be removed later and is not the part of the database design.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'tenants'
    ) THEN
        RAISE EXCEPTION 'Required base table "tenants" not found. Run db/init_agents_db.sql first.';
    END IF;
END $$;

-- Re-runnable: recreate only the additional practice tables.
DROP TABLE IF EXISTS analytics_tenant_daily_economics;
DROP TABLE IF EXISTS analytics_lead_funnel_events;
DROP TABLE IF EXISTS analytics_ticket_lifecycle_facts;
DROP TABLE IF EXISTS analytics_agent_run_metrics;

-- 1) Agent run fact table (row grain: one synthetic run summary)
CREATE TABLE analytics_agent_run_metrics (
    run_metric_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    run_date DATE NOT NULL,
    run_started_at TIMESTAMPTZ NOT NULL,
    run_finished_at TIMESTAMPTZ NOT NULL,
    agent_id TEXT NOT NULL CHECK (agent_id IN (
        'imel', 'kall', 'leed', 'eko', 'floc', 'ora', 'insi'
    )),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN (
        'inbound_email', 'scheduled_check', 'manual_instruction', 'handoff', 'api_event'
    )),
    outcome_status TEXT NOT NULL CHECK (outcome_status IN (
        'completed', 'needs_human', 'failed', 'canceled'
    )),
    latency_ms INT NOT NULL CHECK (latency_ms BETWEEN 50 AND 900000),
    prompt_tokens INT NOT NULL CHECK (prompt_tokens BETWEEN 0 AND 50000),
    completion_tokens INT NOT NULL CHECK (completion_tokens BETWEEN 0 AND 50000),
    tool_calls INT NOT NULL CHECK (tool_calls BETWEEN 0 AND 30),
    retry_count INT NOT NULL CHECK (retry_count BETWEEN 0 AND 10),
    human_escalation BOOLEAN NOT NULL DEFAULT FALSE,
    model_cost_usd NUMERIC(10,4) NOT NULL CHECK (model_cost_usd >= 0),
    revenue_impact_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (revenue_impact_usd >= 0),
    source_run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (run_finished_at >= run_started_at)
);

CREATE INDEX idx_arm_tenant_date ON analytics_agent_run_metrics(tenant_id, run_date);
CREATE INDEX idx_arm_agent_date ON analytics_agent_run_metrics(agent_id, run_date);
CREATE INDEX idx_arm_outcome ON analytics_agent_run_metrics(outcome_status);

WITH tenant_list AS (
    SELECT
        t.id,
        ROW_NUMBER() OVER (ORDER BY t.id) AS tenant_ord
    FROM tenants t
),
calendar AS (
    SELECT generate_series(
        CURRENT_DATE - INTERVAL '179 day',
        CURRENT_DATE,
        INTERVAL '1 day'
    )::date AS run_date
),
slots AS (
    SELECT generate_series(1, 12) AS slot
),
seed AS (
    SELECT
        tl.id AS tenant_id,
        tl.tenant_ord,
        c.run_date,
        s.slot,
        (('x' || substr(md5(concat_ws('|', 'a', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_a,
        (('x' || substr(md5(concat_ws('|', 'b', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_b,
        (('x' || substr(md5(concat_ws('|', 'c', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_c,
        (('x' || substr(md5(concat_ws('|', 'd', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_d,
        (('x' || substr(md5(concat_ws('|', 'e', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_e,
        (('x' || substr(md5(concat_ws('|', 'f', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_f,
        (('x' || substr(md5(concat_ws('|', 'g', tl.id, c.run_date::text, s.slot::text)), 1, 8))::bit(32)::bigint) AS h_g
    FROM tenant_list tl
    CROSS JOIN calendar c
    CROSS JOIN slots s
),
prepared AS (
    SELECT
        tenant_id,
        run_date,
        (
            run_date::timestamptz
            + make_interval(
                hours => ((slot * 2 + tenant_ord) % 24)::int,
                mins => (h_a % 60)::int
            )
        ) AS run_started_at,
        (150 + (h_b % 240000)::int) AS latency_ms,
        CASE
            WHEN (h_c % 100) < 82 THEN 'completed'
            WHEN (h_c % 100) < 90 THEN 'needs_human'
            WHEN (h_c % 100) < 97 THEN 'failed'
            ELSE 'canceled'
        END AS outcome_status,
        CASE (h_d % 7)
            WHEN 0 THEN 'imel'
            WHEN 1 THEN 'kall'
            WHEN 2 THEN 'leed'
            WHEN 3 THEN 'eko'
            WHEN 4 THEN 'floc'
            WHEN 5 THEN 'ora'
            ELSE 'insi'
        END AS agent_id,
        CASE (h_e % 5)
            WHEN 0 THEN 'inbound_email'
            WHEN 1 THEN 'scheduled_check'
            WHEN 2 THEN 'manual_instruction'
            WHEN 3 THEN 'handoff'
            ELSE 'api_event'
        END AS trigger_type,
        (150 + (h_f % 4300)::int) AS prompt_tokens,
        (80 + (h_g % 2100)::int) AS completion_tokens,
        (h_a % 8)::int AS tool_calls,
        h_a,
        h_b,
        h_c,
        h_d,
        h_e,
        h_f
    FROM seed
)
INSERT INTO analytics_agent_run_metrics (
    tenant_id,
    run_date,
    run_started_at,
    run_finished_at,
    agent_id,
    trigger_type,
    outcome_status,
    latency_ms,
    prompt_tokens,
    completion_tokens,
    tool_calls,
    retry_count,
    human_escalation,
    model_cost_usd,
    revenue_impact_usd,
    source_run_id
)
SELECT
    p.tenant_id,
    p.run_date,
    p.run_started_at,
    p.run_started_at + make_interval(secs => GREATEST(1, p.latency_ms / 1000)),
    p.agent_id,
    p.trigger_type,
    p.outcome_status,
    p.latency_ms,
    p.prompt_tokens,
    p.completion_tokens,
    p.tool_calls,
    CASE
        WHEN p.outcome_status = 'failed' THEN 1 + (p.h_d % 3)::int
        WHEN p.outcome_status = 'needs_human' THEN (p.h_d % 2)::int
        ELSE 0
    END AS retry_count,
    (
        p.outcome_status = 'needs_human'
        OR (p.h_e % 100) < 8
    ) AS human_escalation,
    ROUND(
        (
            (p.prompt_tokens + p.completion_tokens)::numeric / 1000
        ) * (
            0.0012 + ((p.h_f % 8)::numeric / 10000)
        ),
        4
    ) AS model_cost_usd,
    CASE
        WHEN p.outcome_status = 'completed'
            THEN ROUND((20 + (p.h_b % 9000)::numeric) / 100, 2)
        WHEN p.outcome_status = 'needs_human'
            THEN ROUND((5 + (p.h_b % 1500)::numeric) / 100, 2)
        ELSE 0
    END AS revenue_impact_usd,
    NULL::UUID AS source_run_id
FROM prepared p;

-- 2) Ticket lifecycle fact table (row grain: one resolved ticket workflow)
CREATE TABLE analytics_ticket_lifecycle_facts (
    ticket_fact_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    synthetic_ticket_key TEXT NOT NULL,
    originating_run_metric_id BIGINT NOT NULL REFERENCES analytics_agent_run_metrics(run_metric_id) ON DELETE RESTRICT,
    ticket_type TEXT NOT NULL CHECK (ticket_type IN (
        'cancel_order', 'complaint', 'billing_issue', 'delivery_issue', 'feature_request'
    )),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    created_at TIMESTAMPTZ NOT NULL,
    first_response_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    response_minutes INT NOT NULL CHECK (response_minutes BETWEEN 1 AND 10080),
    resolution_minutes INT NOT NULL CHECK (resolution_minutes BETWEEN 1 AND 43200),
    status_at_close TEXT NOT NULL CHECK (status_at_close IN ('resolved', 'closed')),
    sla_first_response_minutes INT NOT NULL CHECK (sla_first_response_minutes > 0),
    sla_resolution_minutes INT NOT NULL CHECK (sla_resolution_minutes > 0),
    breached_first_response_sla BOOLEAN NOT NULL,
    breached_resolution_sla BOOLEAN NOT NULL,
    reopen_count INT NOT NULL DEFAULT 0 CHECK (reopen_count BETWEEN 0 AND 8),
    handoff_count INT NOT NULL DEFAULT 0 CHECK (handoff_count BETWEEN 0 AND 20),
    csat_score INT CHECK (csat_score BETWEEN 1 AND 5),
    compensation_usd NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (compensation_usd >= 0),
    CHECK (first_response_at >= created_at),
    CHECK (resolved_at >= first_response_at),
    CHECK (resolution_minutes >= response_minutes),
    UNIQUE (tenant_id, synthetic_ticket_key)
);

CREATE INDEX idx_atlf_tenant_created ON analytics_ticket_lifecycle_facts(tenant_id, created_at);
CREATE INDEX idx_atlf_priority ON analytics_ticket_lifecycle_facts(priority);
CREATE INDEX idx_atlf_sla_flags ON analytics_ticket_lifecycle_facts(breached_first_response_sla, breached_resolution_sla);

WITH tenant_list AS (
    SELECT
        t.id,
        ROW_NUMBER() OVER (ORDER BY t.id) AS tenant_ord
    FROM tenants t
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
arm_index AS (
    SELECT
        arm.run_metric_id,
        arm.tenant_id,
        arm.run_started_at,
        ROW_NUMBER() OVER (PARTITION BY arm.tenant_id ORDER BY arm.run_metric_id) AS rn,
        COUNT(*) OVER (PARTITION BY arm.tenant_id) AS cnt
    FROM analytics_agent_run_metrics arm
),
ticket_seed AS (
    SELECT
        gs.ticket_seq,
        tl.id AS tenant_id,
        tl.tenant_ord,
        (('x' || substr(md5(concat_ws('|', 't1', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 't2', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 't3', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h3,
        (('x' || substr(md5(concat_ws('|', 't4', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h4,
        (('x' || substr(md5(concat_ws('|', 't5', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h5,
        (('x' || substr(md5(concat_ws('|', 't6', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h6,
        (('x' || substr(md5(concat_ws('|', 't7', gs.ticket_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h7
    FROM generate_series(1, 3000) AS gs(ticket_seq)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.ticket_seq - 1) % tm.tenant_count)
),
picked_run AS (
    SELECT
        ts.*,
        ai.run_metric_id,
        ai.run_started_at
    FROM ticket_seed ts
    JOIN arm_index ai
      ON ai.tenant_id = ts.tenant_id
     AND ai.rn = 1 + ((ts.ticket_seq * 11 + ts.tenant_ord) % ai.cnt)
),
prepared AS (
    SELECT
        pr.tenant_id,
        pr.ticket_seq,
        pr.run_metric_id,
        (pr.run_started_at + make_interval(mins => (pr.h1 % 720)::int)) AS created_at,
        (5 + (pr.h2 % 180)::int) AS response_minutes,
        CASE
            WHEN (pr.h3 % 100) < 28 THEN 'cancel_order'
            WHEN (pr.h3 % 100) < 55 THEN 'complaint'
            WHEN (pr.h3 % 100) < 75 THEN 'billing_issue'
            WHEN (pr.h3 % 100) < 92 THEN 'delivery_issue'
            ELSE 'feature_request'
        END AS ticket_type,
        CASE
            WHEN (pr.h4 % 100) < 18 THEN 'urgent'
            WHEN (pr.h4 % 100) < 45 THEN 'high'
            WHEN (pr.h4 % 100) < 82 THEN 'normal'
            ELSE 'low'
        END AS priority,
        pr.h5,
        pr.h6,
        pr.h7
    FROM picked_run pr
),
materialized AS (
    SELECT
        p.*,
        (p.response_minutes + 15 + (p.h5 % 4200)::int) AS resolution_minutes,
        CASE
            WHEN p.priority = 'urgent' THEN 15
            WHEN p.priority = 'high' THEN 45
            WHEN p.priority = 'normal' THEN 120
            ELSE 360
        END AS sla_first_response_minutes,
        CASE
            WHEN p.priority = 'urgent' THEN 180
            WHEN p.priority = 'high' THEN 720
            WHEN p.priority = 'normal' THEN 1440
            ELSE 2880
        END AS sla_resolution_minutes
    FROM prepared p
)
INSERT INTO analytics_ticket_lifecycle_facts (
    tenant_id,
    synthetic_ticket_key,
    originating_run_metric_id,
    ticket_type,
    priority,
    created_at,
    first_response_at,
    resolved_at,
    response_minutes,
    resolution_minutes,
    status_at_close,
    sla_first_response_minutes,
    sla_resolution_minutes,
    breached_first_response_sla,
    breached_resolution_sla,
    reopen_count,
    handoff_count,
    csat_score,
    compensation_usd
)
SELECT
    m.tenant_id,
    m.tenant_id || '-TK-' || LPAD(m.ticket_seq::text, 6, '0') AS synthetic_ticket_key,
    m.run_metric_id AS originating_run_metric_id,
    m.ticket_type,
    m.priority,
    m.created_at,
    m.created_at + make_interval(mins => m.response_minutes),
    m.created_at + make_interval(mins => m.resolution_minutes),
    m.response_minutes,
    m.resolution_minutes,
    CASE
        WHEN (m.h6 % 100) < 88 THEN 'resolved'
        ELSE 'closed'
    END AS status_at_close,
    m.sla_first_response_minutes,
    m.sla_resolution_minutes,
    (m.response_minutes > m.sla_first_response_minutes) AS breached_first_response_sla,
    (m.resolution_minutes > m.sla_resolution_minutes) AS breached_resolution_sla,
    CASE
        WHEN (m.h7 % 100) < 72 THEN 0
        WHEN (m.h7 % 100) < 92 THEN 1
        ELSE 2 + (m.h7 % 3)::int
    END AS reopen_count,
    CASE
        WHEN m.priority IN ('urgent', 'high') THEN 1 + (m.h6 % 6)::int
        ELSE (m.h6 % 3)::int
    END AS handoff_count,
    CASE
        WHEN (m.h5 % 100) < 8 THEN NULL
        ELSE 1 + (m.h5 % 5)::int
    END AS csat_score,
    CASE
        WHEN (m.resolution_minutes > m.sla_resolution_minutes)
            THEN ROUND((10 + (m.h7 % 7000)::numeric) / 100, 2)
        ELSE ROUND((m.h7 % 900)::numeric / 100, 2)
    END AS compensation_usd
FROM materialized m;

-- 3) Lead funnel events (row grain: one stage event for one synthetic lead)
CREATE TABLE analytics_lead_funnel_events (
    lead_event_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL,
    campaign_id TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN (
        'captured', 'enriched', 'validated', 'outreach_sent',
        'opened', 'replied', 'qualified', 'meeting_booked', 'disqualified'
    )),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'linkedin', 'phone', 'web', 'referral')),
    agent_id TEXT NOT NULL CHECK (agent_id IN ('leed', 'eko', 'imel', 'kall', 'floc')),
    event_at TIMESTAMPTZ NOT NULL,
    first_touch_run_metric_id BIGINT NOT NULL REFERENCES analytics_agent_run_metrics(run_metric_id) ON DELETE RESTRICT,
    event_value_usd NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (event_value_usd >= 0),
    processing_ms INT NOT NULL CHECK (processing_ms BETWEEN 10 AND 120000),
    is_positive BOOLEAN NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_alfe_tenant_stage_time ON analytics_lead_funnel_events(tenant_id, stage, event_at);
CREATE INDEX idx_alfe_lead_time ON analytics_lead_funnel_events(lead_id, event_at);
CREATE INDEX idx_alfe_campaign ON analytics_lead_funnel_events(campaign_id);

WITH tenant_list AS (
    SELECT
        t.id,
        ROW_NUMBER() OVER (ORDER BY t.id) AS tenant_ord
    FROM tenants t
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
arm_index AS (
    SELECT
        arm.run_metric_id,
        arm.tenant_id,
        ROW_NUMBER() OVER (PARTITION BY arm.tenant_id ORDER BY arm.run_metric_id) AS rn,
        COUNT(*) OVER (PARTITION BY arm.tenant_id) AS cnt
    FROM analytics_agent_run_metrics arm
),
lead_seed AS (
    SELECT
        gs.event_seq,
        tl.id AS tenant_id,
        tl.tenant_ord,
        1 + ((gs.event_seq * 3 + tl.tenant_ord) % 1800) AS lead_num,
        (('x' || substr(md5(concat_ws('|', 'l1', gs.event_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'l2', gs.event_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 'l3', gs.event_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h3,
        (('x' || substr(md5(concat_ws('|', 'l4', gs.event_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h4,
        (('x' || substr(md5(concat_ws('|', 'l5', gs.event_seq::text, tl.id)), 1, 8))::bit(32)::bigint) AS h5
    FROM generate_series(1, 6200) AS gs(event_seq)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.event_seq - 1) % tm.tenant_count)
),
prepared AS (
    SELECT
        ls.*,
        md5(concat_ws('|', ls.tenant_id, ls.lead_num::text)) AS lead_hash
    FROM lead_seed ls
),
picked_run AS (
    SELECT
        p.*,
        ai.run_metric_id
    FROM prepared p
    JOIN arm_index ai
      ON ai.tenant_id = p.tenant_id
     AND ai.rn = 1 + ((p.event_seq * 7 + p.tenant_ord) % ai.cnt)
)
INSERT INTO analytics_lead_funnel_events (
    tenant_id,
    lead_id,
    campaign_id,
    stage,
    channel,
    agent_id,
    event_at,
    first_touch_run_metric_id,
    event_value_usd,
    processing_ms,
    is_positive,
    metadata
)
SELECT
    pr.tenant_id,
    (
        substr(pr.lead_hash, 1, 8) || '-' ||
        substr(pr.lead_hash, 9, 4) || '-' ||
        substr(pr.lead_hash, 13, 4) || '-' ||
        substr(pr.lead_hash, 17, 4) || '-' ||
        substr(pr.lead_hash, 21, 12)
    )::uuid AS lead_id,
    'CMP-' || LPAD(((pr.h1 % 25) + 1)::text, 3, '0') AS campaign_id,
    CASE
        WHEN (pr.h2 % 100) < 20 THEN 'captured'
        WHEN (pr.h2 % 100) < 34 THEN 'enriched'
        WHEN (pr.h2 % 100) < 47 THEN 'validated'
        WHEN (pr.h2 % 100) < 65 THEN 'outreach_sent'
        WHEN (pr.h2 % 100) < 77 THEN 'opened'
        WHEN (pr.h2 % 100) < 87 THEN 'replied'
        WHEN (pr.h2 % 100) < 94 THEN 'qualified'
        WHEN (pr.h2 % 100) < 97 THEN 'meeting_booked'
        ELSE 'disqualified'
    END AS stage,
    CASE (pr.h3 % 5)
        WHEN 0 THEN 'email'
        WHEN 1 THEN 'linkedin'
        WHEN 2 THEN 'phone'
        WHEN 3 THEN 'web'
        ELSE 'referral'
    END AS channel,
    CASE (pr.h4 % 5)
        WHEN 0 THEN 'leed'
        WHEN 1 THEN 'eko'
        WHEN 2 THEN 'imel'
        WHEN 3 THEN 'kall'
        ELSE 'floc'
    END AS agent_id,
    (
        (CURRENT_DATE - ((pr.h5 % 240)::int))::timestamptz
        + make_interval(hours => (pr.h3 % 24)::int, mins => (pr.h1 % 60)::int)
    ) AS event_at,
    pr.run_metric_id AS first_touch_run_metric_id,
    CASE
        WHEN (pr.h2 % 100) BETWEEN 94 AND 96 THEN ROUND((400 + (pr.h5 % 12000)::numeric) / 100, 2)
        WHEN (pr.h2 % 100) BETWEEN 87 AND 93 THEN ROUND((100 + (pr.h5 % 3500)::numeric) / 100, 2)
        WHEN (pr.h2 % 100) BETWEEN 77 AND 86 THEN ROUND((10 + (pr.h5 % 1200)::numeric) / 100, 2)
        ELSE ROUND((pr.h5 % 500)::numeric / 100, 2)
    END AS event_value_usd,
    (80 + (pr.h4 % 7000)::int) AS processing_ms,
    ((pr.h2 % 100) BETWEEN 77 AND 96) AS is_positive,
    jsonb_build_object(
        'lead_score', (pr.h3 % 100)::int,
        'sequence_step', 1 + (pr.h4 % 8)::int,
        'source', CASE (pr.h3 % 5)
            WHEN 0 THEN 'email'
            WHEN 1 THEN 'linkedin'
            WHEN 2 THEN 'phone'
            WHEN 3 THEN 'web'
            ELSE 'referral'
        END,
        'intent_bucket', CASE
            WHEN (pr.h1 % 100) < 30 THEN 'low'
            WHEN (pr.h1 % 100) < 70 THEN 'medium'
            ELSE 'high'
        END
    ) AS metadata
FROM picked_run pr;

-- 4) Tenant daily economics table (row grain: tenant + day aggregate)
CREATE TABLE analytics_tenant_daily_economics (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    active_runs INT NOT NULL DEFAULT 0 CHECK (active_runs >= 0),
    successful_runs INT NOT NULL DEFAULT 0 CHECK (successful_runs >= 0),
    failed_runs INT NOT NULL DEFAULT 0 CHECK (failed_runs >= 0),
    human_escalations INT NOT NULL DEFAULT 0 CHECK (human_escalations >= 0),
    tickets_created INT NOT NULL DEFAULT 0 CHECK (tickets_created >= 0),
    tickets_closed INT NOT NULL DEFAULT 0 CHECK (tickets_closed >= 0),
    lead_events INT NOT NULL DEFAULT 0 CHECK (lead_events >= 0),
    meetings_booked INT NOT NULL DEFAULT 0 CHECK (meetings_booked >= 0),
    gross_revenue_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (gross_revenue_usd >= 0),
    llm_cost_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (llm_cost_usd >= 0),
    support_credits_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (support_credits_usd >= 0),
    gross_margin_usd NUMERIC(12,2) NOT NULL,
    net_retention_rate NUMERIC(5,2) NOT NULL CHECK (net_retention_rate BETWEEN 0 AND 200),
    nps_score INT NOT NULL CHECK (nps_score BETWEEN -100 AND 100),
    PRIMARY KEY (tenant_id, metric_date),
    CHECK (successful_runs <= active_runs),
    CHECK (failed_runs <= active_runs),
    CHECK (human_escalations <= active_runs),
    CHECK (meetings_booked <= lead_events)
);

CREATE INDEX idx_atde_date ON analytics_tenant_daily_economics(metric_date);

WITH tenant_list AS (
    SELECT t.id FROM tenants t
),
calendar AS (
    SELECT generate_series(
        CURRENT_DATE - INTERVAL '364 day',
        CURRENT_DATE,
        INTERVAL '1 day'
    )::date AS metric_date
),
run_daily AS (
    SELECT
        arm.tenant_id,
        arm.run_date AS metric_date,
        COUNT(*) AS active_runs,
        COUNT(*) FILTER (WHERE arm.outcome_status = 'completed') AS successful_runs,
        COUNT(*) FILTER (WHERE arm.outcome_status = 'failed') AS failed_runs,
        COUNT(*) FILTER (WHERE arm.human_escalation) AS human_escalations,
        ROUND(COALESCE(SUM(arm.model_cost_usd), 0), 2) AS llm_cost_usd,
        ROUND(COALESCE(SUM(arm.revenue_impact_usd), 0), 2) AS gross_revenue_usd
    FROM analytics_agent_run_metrics arm
    GROUP BY arm.tenant_id, arm.run_date
),
ticket_daily AS (
    SELECT
        tlf.tenant_id,
        tlf.created_at::date AS metric_date,
        COUNT(*) AS tickets_created,
        COUNT(*) FILTER (WHERE tlf.status_at_close IN ('resolved', 'closed')) AS tickets_closed,
        ROUND(COALESCE(SUM(tlf.compensation_usd), 0), 2) AS support_credits_usd
    FROM analytics_ticket_lifecycle_facts tlf
    GROUP BY tlf.tenant_id, tlf.created_at::date
),
lead_daily AS (
    SELECT
        lfe.tenant_id,
        lfe.event_at::date AS metric_date,
        COUNT(*) AS lead_events,
        COUNT(*) FILTER (WHERE lfe.stage = 'meeting_booked') AS meetings_booked
    FROM analytics_lead_funnel_events lfe
    GROUP BY lfe.tenant_id, lfe.event_at::date
),
scored AS (
    SELECT
        tl.id AS tenant_id,
        c.metric_date,
        COALESCE(rd.active_runs, 0) AS active_runs,
        COALESCE(rd.successful_runs, 0) AS successful_runs,
        COALESCE(rd.failed_runs, 0) AS failed_runs,
        COALESCE(rd.human_escalations, 0) AS human_escalations,
        COALESCE(td.tickets_created, 0) AS tickets_created,
        COALESCE(td.tickets_closed, 0) AS tickets_closed,
        COALESCE(ld.lead_events, 0) AS lead_events,
        COALESCE(ld.meetings_booked, 0) AS meetings_booked,
        COALESCE(rd.gross_revenue_usd, 0)::numeric(12,2) AS gross_revenue_usd,
        COALESCE(rd.llm_cost_usd, 0)::numeric(12,2) AS llm_cost_usd,
        COALESCE(td.support_credits_usd, 0)::numeric(12,2) AS support_credits_usd,
        (
            80
            + (
                (('x' || substr(md5(concat_ws('|', 'nrr', tl.id, c.metric_date::text)), 1, 8))::bit(32)::bigint % 3600)::numeric
                / 100
            )
        )::numeric(5,2) AS net_retention_rate,
        (
            -20
            + (('x' || substr(md5(concat_ws('|', 'nps', tl.id, c.metric_date::text)), 1, 8))::bit(32)::bigint % 101)::int
        ) AS nps_score
    FROM tenant_list tl
    CROSS JOIN calendar c
    LEFT JOIN run_daily rd
      ON rd.tenant_id = tl.id
     AND rd.metric_date = c.metric_date
    LEFT JOIN ticket_daily td
      ON td.tenant_id = tl.id
     AND td.metric_date = c.metric_date
    LEFT JOIN lead_daily ld
      ON ld.tenant_id = tl.id
     AND ld.metric_date = c.metric_date
)
INSERT INTO analytics_tenant_daily_economics (
    tenant_id,
    metric_date,
    active_runs,
    successful_runs,
    failed_runs,
    human_escalations,
    tickets_created,
    tickets_closed,
    lead_events,
    meetings_booked,
    gross_revenue_usd,
    llm_cost_usd,
    support_credits_usd,
    gross_margin_usd,
    net_retention_rate,
    nps_score
)
SELECT
    s.tenant_id,
    s.metric_date,
    s.active_runs,
    s.successful_runs,
    s.failed_runs,
    s.human_escalations,
    s.tickets_created,
    s.tickets_closed,
    s.lead_events,
    s.meetings_booked,
    s.gross_revenue_usd,
    s.llm_cost_usd,
    s.support_credits_usd,
    (s.gross_revenue_usd - s.llm_cost_usd - s.support_credits_usd)::numeric(12,2) AS gross_margin_usd,
    s.net_retention_rate,
    s.nps_score
FROM scored s;

COMMIT;

-- Quick row-count validation (expected total > 8,000 rows across these tables).
SELECT 'analytics_agent_run_metrics' AS table_name, COUNT(*)::bigint AS row_count FROM analytics_agent_run_metrics
UNION ALL
SELECT 'analytics_ticket_lifecycle_facts', COUNT(*)::bigint FROM analytics_ticket_lifecycle_facts
UNION ALL
SELECT 'analytics_lead_funnel_events', COUNT(*)::bigint FROM analytics_lead_funnel_events
UNION ALL
SELECT 'analytics_tenant_daily_economics', COUNT(*)::bigint FROM analytics_tenant_daily_economics
ORDER BY table_name;
