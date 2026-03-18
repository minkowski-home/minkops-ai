-- db/02_base_table_enrichment.sql
--
-- Purpose:
--   Populate the actual application tables created by db/01_schema.sql with a large,
--   realistic interaction dataset without modifying db/01_bootstrap.sql or db/01_schema.sql.
--
-- Notes:
--   - Re-runnable: inserts deterministic ids and uses conflict-safe inserts
--   - Safe to run after db/01_schema.sql
--   - Complements db/real_world_enrichment.sql but does not require it

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'tenants'
    ) THEN
        RAISE EXCEPTION 'Required base table "tenants" not found. Run db/01_schema.sql first.';
    END IF;
END $$;

-- Extend the tenant universe beyond the tiny schema seed.
INSERT INTO tenants (id, name, config, enabled)
VALUES
    ('northstar_design', 'Northstar Design', '{"region":"ca-central-1","plan":"growth","segment":"interior-design"}'::jsonb, TRUE),
    ('loftandco_hospitality', 'Loft & Co Hospitality', '{"region":"us-east-1","plan":"enterprise","segment":"hospitality"}'::jsonb, TRUE),
    ('atlas_retail_group', 'Atlas Retail Group', '{"region":"us-west-2","plan":"enterprise","segment":"retail"}'::jsonb, TRUE),
    ('terra_workspace', 'Terra Workspace', '{"region":"eu-west-1","plan":"growth","segment":"workspace"}'::jsonb, TRUE),
    ('oakwell_properties', 'Oakwell Properties', '{"region":"ca-central-1","plan":"starter","segment":"real-estate"}'::jsonb, TRUE),
    ('nimbus_health_spaces', 'Nimbus Health Spaces', '{"region":"us-east-2","plan":"growth","segment":"healthcare"}'::jsonb, TRUE)
ON CONFLICT (id) DO UPDATE
SET
    name = EXCLUDED.name,
    config = EXCLUDED.config,
    enabled = EXCLUDED.enabled;

-- Users
WITH tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        md5(concat_ws('|', 'user', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 'u1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'u2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2
    FROM generate_series(1, 720) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO users (
    id,
    tenant_id,
    email,
    password_hash,
    role,
    is_active
)
SELECT
    (
        substr(hash_key, 1, 8) || '-' ||
        substr(hash_key, 9, 4) || '-' ||
        substr(hash_key, 13, 4) || '-' ||
        substr(hash_key, 17, 4) || '-' ||
        substr(hash_key, 21, 12)
    )::uuid AS id,
    tenant_id,
    CASE
        WHEN (h1 % 100) < 4 THEN 'admin+' || lower(substr(hash_key, 1, 10)) || '@example.com'
        WHEN (h1 % 100) < 18 THEN 'manager+' || lower(substr(hash_key, 1, 10)) || '@example.com'
        ELSE 'member+' || lower(substr(hash_key, 1, 10)) || '@example.com'
    END AS email,
    'argon2id$synthetic$' || substr(hash_key, 1, 32) AS password_hash,
    CASE
        WHEN (h1 % 100) < 4 THEN 'admin'
        WHEN (h1 % 100) < 18 THEN 'manager'
        ELSE 'member'
    END AS role,
    ((h2 % 100) >= 3) AS is_active
FROM seed
ON CONFLICT (id) DO NOTHING;

-- Refresh tokens
WITH user_index AS (
    SELECT
        id AS user_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM users
),
tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        tl.tenant_ord,
        md5(concat_ws('|', 'rt', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 'rt1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'rt2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2
    FROM generate_series(1, 1800) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO refresh_tokens (
    id,
    user_id,
    token_hash,
    expires_at,
    created_at,
    revoked
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS id,
    ui.user_id,
    'sha256:' || s.hash_key AS token_hash,
    (
        CURRENT_DATE
        + ((7 + (s.h1 % 45))::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS expires_at,
    (
        CURRENT_DATE
        - ((s.h1 % 60)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS created_at,
    ((s.h2 % 100) < 14) AS revoked
FROM seed s
JOIN user_index ui
  ON ui.tenant_id = s.tenant_id
 AND ui.rn = 1 + ((s.seed_id * 7 + s.tenant_ord) % ui.cnt)
ON CONFLICT (id) DO NOTHING;

-- Runs
WITH tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        tl.tenant_ord,
        md5(concat_ws('|', 'run', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 'r1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'r2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 'r3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h3,
        (('x' || substr(md5(concat_ws('|', 'r4', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h4
    FROM generate_series(1, 36000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO runs (
    id,
    tenant_id,
    agent_id,
    status,
    input_payload,
    created_at,
    updated_at
)
SELECT
    (
        substr(hash_key, 1, 8) || '-' ||
        substr(hash_key, 9, 4) || '-' ||
        substr(hash_key, 13, 4) || '-' ||
        substr(hash_key, 17, 4) || '-' ||
        substr(hash_key, 21, 12)
    )::uuid AS id,
    tenant_id,
    CASE (h1 % 7)
        WHEN 0 THEN 'imel'
        WHEN 1 THEN 'kall'
        WHEN 2 THEN 'leed'
        WHEN 3 THEN 'eko'
        WHEN 4 THEN 'floc'
        WHEN 5 THEN 'ora'
        ELSE 'insi'
    END AS agent_id,
    CASE
        WHEN (h2 % 100) < 8 THEN 'queued'
        WHEN (h2 % 100) < 15 THEN 'running'
        WHEN (h2 % 100) < 82 THEN 'completed'
        WHEN (h2 % 100) < 95 THEN 'failed'
        ELSE 'sleeping'
    END AS status,
    jsonb_build_object(
        'trigger_kind', CASE (h3 % 5)
            WHEN 0 THEN 'email'
            WHEN 1 THEN 'handoff'
            WHEN 2 THEN 'human_instruction'
            WHEN 3 THEN 'scheduler'
            ELSE 'api_event'
        END,
        'priority', CASE
            WHEN (h4 % 100) < 10 THEN 'urgent'
            WHEN (h4 % 100) < 28 THEN 'high'
            WHEN (h4 % 100) < 72 THEN 'normal'
            ELSE 'low'
        END,
        'synthetic', true,
        'customer_email', 'contact+' || lower(substr(hash_key, 1, 10)) || '@example.com'
    ) AS input_payload,
    (
        CURRENT_DATE
        - ((h1 % 365)::int || ' days')::interval
        + make_interval(hours => (h2 % 24)::int, mins => (h3 % 60)::int)
    )::timestamptz AS created_at,
    (
        CURRENT_DATE
        - ((h1 % 365)::int || ' days')::interval
        + make_interval(
            hours => (h2 % 24)::int,
            mins => (((h3 % 60) + ((h4 % 80) + 1))::int)
        )
    )::timestamptz AS updated_at
FROM seed
ON CONFLICT (id) DO NOTHING;

-- Agent state checkpoints
INSERT INTO agent_state (
    run_id,
    checkpoint_id,
    state_data,
    node_name,
    created_at
)
SELECT
    r.id AS run_id,
    1 + (ABS(('x' || substr(md5(r.id::text || ':cp'), 1, 8))::bit(32)::bigint) % 5)::int AS checkpoint_id,
    jsonb_build_object(
        'action', CASE r.status
            WHEN 'completed' THEN 'respond'
            WHEN 'failed' THEN 'error'
            WHEN 'sleeping' THEN 'await_human'
            ELSE 'processing'
        END,
        'agent_id', r.agent_id,
        'tenant_id', r.tenant_id,
        'synthetic', true
    ) AS state_data,
    CASE r.status
        WHEN 'completed' THEN '__end__'
        WHEN 'failed' THEN 'retry_or_fail'
        WHEN 'sleeping' THEN 'awaiting_input'
        ELSE 'route'
    END AS node_name,
    r.updated_at AS created_at
FROM runs r
ON CONFLICT (run_id) DO NOTHING;

-- Messages: three turns per run for conversation-heavy data.
INSERT INTO messages (
    id,
    run_id,
    tenant_id,
    role,
    content,
    meta,
    created_at
)
SELECT
    (
        substr(md5(concat_ws('|', 'msg', r.id::text, seq.n::text)), 1, 8) || '-' ||
        substr(md5(concat_ws('|', 'msg', r.id::text, seq.n::text)), 9, 4) || '-' ||
        substr(md5(concat_ws('|', 'msg', r.id::text, seq.n::text)), 13, 4) || '-' ||
        substr(md5(concat_ws('|', 'msg', r.id::text, seq.n::text)), 17, 4) || '-' ||
        substr(md5(concat_ws('|', 'msg', r.id::text, seq.n::text)), 21, 12)
    )::uuid AS id,
    r.id AS run_id,
    r.tenant_id,
    CASE seq.n
        WHEN 1 THEN 'user'
        WHEN 2 THEN 'assistant'
        ELSE 'tool'
    END AS role,
    CASE seq.n
        WHEN 1 THEN 'Inbound request received from customer or internal trigger.'
        WHEN 2 THEN 'Agent classified intent and prepared next action.'
        ELSE 'Tool invocation completed and state persisted.'
    END AS content,
    jsonb_build_object('synthetic', true, 'message_seq', seq.n) AS meta,
    r.created_at + make_interval(mins => seq.n::int) AS created_at
FROM runs r
CROSS JOIN generate_series(1, 3) AS seq(n)
ON CONFLICT (id) DO NOTHING;

-- Tickets
WITH run_index AS (
    SELECT
        id AS run_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM runs
),
tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        tl.tenant_ord,
        md5(concat_ws('|', 'ticket', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 't1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 't2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 't3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h3
    FROM generate_series(1, 9000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO tickets (
    id,
    tenant_id,
    email_id,
    ticket_type,
    status,
    priority,
    sender_email,
    summary,
    raw_email,
    created_at,
    updated_at
)
SELECT
    (
        substr(hash_key, 1, 8) || '-' ||
        substr(hash_key, 9, 4) || '-' ||
        substr(hash_key, 13, 4) || '-' ||
        substr(hash_key, 17, 4) || '-' ||
        substr(hash_key, 21, 12)
    )::uuid AS id,
    s.tenant_id,
    'email-' || lower(substr(hash_key, 1, 14)) AS email_id,
    CASE
        WHEN (h1 % 100) < 42 THEN 'complaint'
        ELSE 'cancel_order'
    END AS ticket_type,
    CASE
        WHEN (h2 % 100) < 18 THEN 'open'
        WHEN (h2 % 100) < 45 THEN 'in_progress'
        WHEN (h2 % 100) < 82 THEN 'resolved'
        ELSE 'closed'
    END AS status,
    CASE
        WHEN (h3 % 100) < 10 THEN 'urgent'
        WHEN (h3 % 100) < 30 THEN 'high'
        ELSE 'normal'
    END AS priority,
    'support+' || lower(substr(hash_key, 1, 10)) || '@example.com' AS sender_email,
    CASE
        WHEN (h1 % 100) < 42 THEN 'Customer reported a service or delivery issue.'
        ELSE 'Customer requested to cancel an order before completion.'
    END AS summary,
    'Synthetic inbound email thread for SQL practice.' AS raw_email,
    (
        CURRENT_DATE
        - ((h1 % 320)::int || ' days')::interval
        + make_interval(hours => (h2 % 24)::int)
    )::timestamptz AS created_at,
    (
        CURRENT_DATE
        - ((h1 % 320)::int || ' days')::interval
        + make_interval(hours => (h2 % 24)::int + ((h3 % 48) + 1)::int)
    )::timestamptz AS updated_at
FROM seed s
ON CONFLICT (id) DO NOTHING;

-- Event outbox
WITH run_index AS (
    SELECT
        id AS run_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM runs
),
tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        tl.tenant_ord,
        md5(concat_ws('|', 'outbox', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 'e1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'e2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 'e3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h3
    FROM generate_series(1, 22000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO event_outbox (
    id,
    run_id,
    tenant_id,
    event_type,
    payload,
    idempotency_key,
    status,
    attempts,
    last_error,
    available_at,
    locked_at,
    locked_by,
    processed_at,
    created_at,
    updated_at
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS id,
    ri.run_id,
    s.tenant_id,
    CASE (s.h1 % 6)
        WHEN 0 THEN 'send_email'
        WHEN 1 THEN 'sync_crm'
        WHEN 2 THEN 'trigger_webhook'
        WHEN 3 THEN 'update_order'
        WHEN 4 THEN 'create_ticket'
        ELSE 'post_internal_audit'
    END AS event_type,
    jsonb_build_object(
        'synthetic', true,
        'sequence', s.seed_id,
        'target', CASE (s.h2 % 4)
            WHEN 0 THEN 'email'
            WHEN 1 THEN 'crm'
            WHEN 2 THEN 'webhook'
            ELSE 'ops'
        END
    ) AS payload,
    'outbox-' || s.tenant_id || '-' || s.seed_id::text AS idempotency_key,
    CASE
        WHEN (s.h2 % 100) < 54 THEN 'queued'
        WHEN (s.h2 % 100) < 67 THEN 'processing'
        WHEN (s.h2 % 100) < 89 THEN 'succeeded'
        WHEN (s.h2 % 100) < 97 THEN 'failed'
        ELSE 'dead'
    END AS status,
    (s.h3 % 4)::int AS attempts,
    CASE
        WHEN (s.h2 % 100) >= 89 THEN 'Transient provider or network failure.'
        ELSE NULL
    END AS last_error,
    (
        CURRENT_DATE
        - ((s.h1 % 200)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS available_at,
    CASE
        WHEN (s.h2 % 100) BETWEEN 54 AND 66 THEN (
            CURRENT_DATE
            - ((s.h1 % 200)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int, mins => 5)
        )::timestamptz
        ELSE NULL
    END AS locked_at,
    CASE
        WHEN (s.h2 % 100) BETWEEN 54 AND 66 THEN 'worker-' || ((s.h3 % 9) + 1)::text
        ELSE NULL
    END AS locked_by,
    CASE
        WHEN (s.h2 % 100) BETWEEN 67 AND 88 THEN (
            CURRENT_DATE
            - ((s.h1 % 200)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int, mins => 11)
        )::timestamptz
        ELSE NULL
    END AS processed_at,
    (
        CURRENT_DATE
        - ((s.h1 % 200)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS created_at,
    (
        CURRENT_DATE
        - ((s.h1 % 200)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int, mins => 20)
    )::timestamptz AS updated_at
FROM seed s
JOIN run_index ri
  ON ri.tenant_id = s.tenant_id
 AND ri.rn = 1 + ((s.seed_id * 11 + s.tenant_ord) % ri.cnt)
ON CONFLICT (id) DO NOTHING;

-- Activity logs derived from runs.
INSERT INTO activity_logs (
    id,
    tenant_id,
    agent_id,
    run_id,
    event,
    summary,
    details,
    created_at
)
SELECT
    (
        substr(md5(concat_ws('|', 'log', r.id::text)), 1, 8) || '-' ||
        substr(md5(concat_ws('|', 'log', r.id::text)), 9, 4) || '-' ||
        substr(md5(concat_ws('|', 'log', r.id::text)), 13, 4) || '-' ||
        substr(md5(concat_ws('|', 'log', r.id::text)), 17, 4) || '-' ||
        substr(md5(concat_ws('|', 'log', r.id::text)), 21, 12)
    )::uuid AS id,
    r.tenant_id,
    r.agent_id,
    r.id AS run_id,
    CASE r.status
        WHEN 'completed' THEN 'processed_interaction'
        WHEN 'failed' THEN 'run_failed'
        WHEN 'sleeping' THEN 'awaiting_human_input'
        ELSE 'run_progressed'
    END AS event,
    'Synthetic audit trail derived from a realistic agent run.' AS summary,
    jsonb_build_object('status', r.status, 'synthetic', true) AS details,
    r.updated_at AS created_at
FROM runs r
ON CONFLICT (id) DO NOTHING;

-- Human instructions queue
WITH run_index AS (
    SELECT
        id AS run_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM runs
),
tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        tl.tenant_ord,
        md5(concat_ws('|', 'hiq', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 'h1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'h2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 'h3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h3,
        (('x' || substr(md5(concat_ws('|', 'h4', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h4
    FROM generate_series(1, 8000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO human_instructions_queue (
    id,
    tenant_id,
    last_run_id,
    author_id,
    target_agent_id,
    target_role,
    assigned_agent_id,
    assigned_by,
    assigned_at,
    instruction,
    payload,
    priority,
    available_at,
    due_at,
    expires_at,
    status,
    attempts,
    max_attempts,
    last_error,
    locked_at,
    locked_by,
    lease_expires_at,
    acknowledged_at,
    acknowledged_by,
    completed_at,
    completed_by,
    agent_response,
    result_payload,
    human_feedback,
    feedback_score,
    idempotency_key,
    created_at,
    updated_at
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS id,
    s.tenant_id,
    ri.run_id AS last_run_id,
    'manager+' || lower(substr(s.hash_key, 1, 10)) || '@example.com' AS author_id,
    CASE (s.h1 % 5)
        WHEN 0 THEN 'imel'
        WHEN 1 THEN 'kall'
        WHEN 2 THEN 'leed'
        WHEN 3 THEN 'eko'
        ELSE NULL
    END AS target_agent_id,
    CASE (s.h2 % 4)
        WHEN 0 THEN 'support'
        WHEN 1 THEN 'sales'
        WHEN 2 THEN 'growth'
        ELSE 'operations'
    END AS target_role,
    CASE
        WHEN (s.h3 % 100) < 82 THEN CASE (s.h1 % 4)
            WHEN 0 THEN 'imel'
            WHEN 1 THEN 'kall'
            WHEN 2 THEN 'leed'
            ELSE 'eko'
        END
        ELSE NULL
    END AS assigned_agent_id,
    CASE WHEN (s.h3 % 100) < 82 THEN 'system_planner' ELSE NULL END AS assigned_by,
    CASE
        WHEN (s.h3 % 100) < 82 THEN (
            CURRENT_DATE
            - ((s.h1 % 180)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int)
        )::timestamptz
        ELSE NULL
    END AS assigned_at,
    CASE (s.h2 % 5)
        WHEN 0 THEN 'Review overnight lead pipeline and highlight risks.'
        WHEN 1 THEN 'Prepare a concise customer follow-up summary.'
        WHEN 2 THEN 'Audit unresolved tickets older than SLA target.'
        WHEN 3 THEN 'Generate a weekly operations status digest.'
        ELSE 'Investigate recent churn signals and propose next actions.'
    END AS instruction,
    jsonb_build_object('synthetic', true, 'sequence', s.seed_id) AS payload,
    CASE
        WHEN (s.h4 % 100) < 8 THEN 'urgent'
        WHEN (s.h4 % 100) < 24 THEN 'high'
        WHEN (s.h4 % 100) < 72 THEN 'normal'
        ELSE 'low'
    END AS priority,
    (
        CURRENT_DATE
        - ((s.h1 % 180)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS available_at,
    (
        CURRENT_DATE
        - ((s.h1 % 180)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int + 24)
    )::timestamptz AS due_at,
    (
        CURRENT_DATE
        - ((s.h1 % 180)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int + 72)
    )::timestamptz AS expires_at,
    CASE
        WHEN (s.h3 % 100) < 26 THEN 'queued'
        WHEN (s.h3 % 100) < 38 THEN 'acknowledged'
        WHEN (s.h3 % 100) < 54 THEN 'in_progress'
        WHEN (s.h3 % 100) < 74 THEN 'completed'
        WHEN (s.h3 % 100) < 84 THEN 'failed'
        WHEN (s.h3 % 100) < 90 THEN 'blocked'
        WHEN (s.h3 % 100) < 96 THEN 'dismissed'
        ELSE 'expired'
    END AS status,
    (s.h4 % 3)::int AS attempts,
    3 AS max_attempts,
    CASE
        WHEN (s.h3 % 100) BETWEEN 74 AND 83 THEN 'Downstream dependency unavailable.'
        ELSE NULL
    END AS last_error,
    CASE
        WHEN (s.h3 % 100) BETWEEN 26 AND 53 THEN (
            CURRENT_DATE
            - ((s.h1 % 180)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int, mins => 15)
        )::timestamptz
        ELSE NULL
    END AS locked_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 26 AND 53 THEN 'ai-suite-worker-' || ((s.h1 % 8) + 1)::text
        ELSE NULL
    END AS locked_by,
    CASE
        WHEN (s.h3 % 100) BETWEEN 26 AND 53 THEN (
            CURRENT_DATE
            - ((s.h1 % 180)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int + 1)
        )::timestamptz
        ELSE NULL
    END AS lease_expires_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 26 AND 73 THEN (
            CURRENT_DATE
            - ((s.h1 % 180)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int, mins => 10)
        )::timestamptz
        ELSE NULL
    END AS acknowledged_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 26 AND 73 THEN 'planner@system'
        ELSE NULL
    END AS acknowledged_by,
    CASE
        WHEN (s.h3 % 100) BETWEEN 54 AND 73 THEN (
            CURRENT_DATE
            - ((s.h1 % 180)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int + ((s.h4 % 10) + 2)::int)
        )::timestamptz
        ELSE NULL
    END AS completed_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 54 AND 73 THEN 'agent-worker'
        ELSE NULL
    END AS completed_by,
    CASE
        WHEN (s.h3 % 100) BETWEEN 54 AND 73 THEN 'Instruction completed with structured output.'
        ELSE NULL
    END AS agent_response,
    CASE
        WHEN (s.h3 % 100) BETWEEN 54 AND 73 THEN jsonb_build_object('result', 'completed', 'synthetic', true)
        ELSE '{}'::jsonb
    END AS result_payload,
    CASE
        WHEN (s.h3 % 100) BETWEEN 54 AND 70 THEN 'Useful output, minor edits required.'
        ELSE NULL
    END AS human_feedback,
    CASE
        WHEN (s.h3 % 100) BETWEEN 54 AND 70 THEN 3 + (s.h2 % 3)::int
        ELSE NULL
    END AS feedback_score,
    'hiq-' || s.tenant_id || '-' || s.seed_id::text AS idempotency_key,
    (
        CURRENT_DATE
        - ((s.h1 % 180)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS created_at,
    (
        CURRENT_DATE
        - ((s.h1 % 180)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int, mins => 25)
    )::timestamptz AS updated_at
FROM seed s
JOIN run_index ri
  ON ri.tenant_id = s.tenant_id
 AND ri.rn = 1 + ((s.seed_id * 5 + s.tenant_ord) % ri.cnt)
ON CONFLICT (id) DO NOTHING;

-- Agent intercom queue
WITH run_index AS (
    SELECT
        id AS run_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM runs
),
tenant_list AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
    FROM tenants
),
tenant_meta AS (
    SELECT COUNT(*)::int AS tenant_count FROM tenant_list
),
seed AS (
    SELECT
        gs.n AS seed_id,
        tl.id AS tenant_id,
        tl.tenant_ord,
        md5(concat_ws('|', 'aiq', tl.id, gs.n::text)) AS hash_key,
        (('x' || substr(md5(concat_ws('|', 'a1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h1,
        (('x' || substr(md5(concat_ws('|', 'a2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h2,
        (('x' || substr(md5(concat_ws('|', 'a3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint) AS h3
    FROM generate_series(1, 16000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO agent_intercom_queue (
    id,
    tenant_id,
    run_id,
    from_agent_id,
    to_agent_id,
    channel,
    kind,
    priority,
    status,
    message,
    payload,
    reply_to,
    expires_at,
    delivered_at,
    consumed_at,
    consumed_by,
    created_at,
    updated_at
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS id,
    s.tenant_id,
    ri.run_id,
    CASE (s.h1 % 6)
        WHEN 0 THEN 'imel'
        WHEN 1 THEN 'kall'
        WHEN 2 THEN 'leed'
        WHEN 3 THEN 'eko'
        WHEN 4 THEN 'floc'
        ELSE 'ora'
    END AS from_agent_id,
    CASE (s.h2 % 6)
        WHEN 0 THEN 'imel'
        WHEN 1 THEN 'kall'
        WHEN 2 THEN 'leed'
        WHEN 3 THEN 'eko'
        WHEN 4 THEN 'floc'
        ELSE 'ora'
    END AS to_agent_id,
    CASE (s.h3 % 4)
        WHEN 0 THEN 'support'
        WHEN 1 THEN 'sales'
        WHEN 2 THEN 'ops'
        ELSE 'human_interrupts'
    END AS channel,
    CASE (s.h1 % 6)
        WHEN 0 THEN 'message'
        WHEN 1 THEN 'instruction'
        WHEN 2 THEN 'question'
        WHEN 3 THEN 'thought'
        WHEN 4 THEN 'handoff'
        ELSE 'signal'
    END AS kind,
    CASE
        WHEN (s.h2 % 100) < 8 THEN 'urgent'
        WHEN (s.h2 % 100) < 22 THEN 'high'
        WHEN (s.h2 % 100) < 70 THEN 'normal'
        ELSE 'low'
    END AS priority,
    CASE
        WHEN (s.h3 % 100) < 40 THEN 'queued'
        WHEN (s.h3 % 100) < 68 THEN 'delivered'
        WHEN (s.h3 % 100) < 88 THEN 'consumed'
        WHEN (s.h3 % 100) < 96 THEN 'archived'
        ELSE 'expired'
    END AS status,
    CASE (s.h1 % 5)
        WHEN 0 THEN 'Please review the attached account context before responding.'
        WHEN 1 THEN 'Customer follow-up required before the next SLA boundary.'
        WHEN 2 THEN 'Escalation path updated after new evidence arrived.'
        WHEN 3 THEN 'Summarize decision rationale for audit log.'
        ELSE 'Handing off ownership to the specialized workflow.'
    END AS message,
    jsonb_build_object('synthetic', true, 'sequence', s.seed_id) AS payload,
    NULL::uuid AS reply_to,
    (
        CURRENT_DATE
        - ((s.h1 % 120)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int + 48)
    )::timestamptz AS expires_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 40 AND 87 THEN (
            CURRENT_DATE
            - ((s.h1 % 120)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int, mins => 7)
        )::timestamptz
        ELSE NULL
    END AS delivered_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 68 AND 87 THEN (
            CURRENT_DATE
            - ((s.h1 % 120)::int || ' days')::interval
            + make_interval(hours => (s.h2 % 24)::int, mins => 21)
        )::timestamptz
        ELSE NULL
    END AS consumed_at,
    CASE
        WHEN (s.h3 % 100) BETWEEN 68 AND 87 THEN 'agent-consumer-' || ((s.h1 % 6) + 1)::text
        ELSE NULL
    END AS consumed_by,
    (
        CURRENT_DATE
        - ((s.h1 % 120)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int)
    )::timestamptz AS created_at,
    (
        CURRENT_DATE
        - ((s.h1 % 120)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int, mins => 25)
    )::timestamptz AS updated_at
FROM seed s
JOIN run_index ri
  ON ri.tenant_id = s.tenant_id
 AND ri.rn = 1 + ((s.seed_id * 13 + s.tenant_ord) % ri.cnt)
ON CONFLICT (id) DO NOTHING;

-- Tenant KB chunks: dynamic insert for either vector or JSON fallback shape.
DO $$
DECLARE
    has_vector_column BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tenant_kb_chunks'
          AND column_name = 'embedding'
    ) INTO has_vector_column;

    IF has_vector_column THEN
        EXECUTE $vector_insert$
            WITH tenant_list AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
                FROM tenants
            ),
            seed AS (
                SELECT
                    tl.id AS tenant_id,
                    gs.n AS seed_id,
                    md5(concat_ws('|', 'kb', tl.id, gs.n::text)) AS hash_key
                FROM tenant_list tl
                CROSS JOIN generate_series(1, 18) AS gs(n)
            )
            INSERT INTO tenant_kb_chunks (
                id,
                tenant_id,
                doc_id,
                source_uri,
                source_type,
                chunk_index,
                content,
                embedding,
                metadata,
                created_at,
                updated_at
            )
            SELECT
                (
                    substr(hash_key, 1, 8) || '-' ||
                    substr(hash_key, 9, 4) || '-' ||
                    substr(hash_key, 13, 4) || '-' ||
                    substr(hash_key, 17, 4) || '-' ||
                    substr(hash_key, 21, 12)
                )::uuid AS id,
                tenant_id,
                'doc-' || substr(hash_key, 1, 12) AS doc_id,
                'synthetic://' || tenant_id || '/doc/' || seed_id::text AS source_uri,
                CASE
                    WHEN seed_id <= 3 THEN 'brand_kit'
                    WHEN seed_id <= 9 THEN 'faq'
                    WHEN seed_id <= 14 THEN 'policy'
                    ELSE 'run_note'
                END AS source_type,
                seed_id AS chunk_index,
                CASE
                    WHEN seed_id <= 3 THEN 'Brand tone and positioning guidance for ' || tenant_id
                    WHEN seed_id <= 9 THEN 'Frequently asked question answer chunk ' || seed_id::text
                    WHEN seed_id <= 14 THEN 'Operational policy chunk ' || seed_id::text
                    ELSE 'Execution note chunk ' || seed_id::text
                END AS content,
                ('[0' || repeat(',0', 1535) || ']')::vector AS embedding,
                jsonb_build_object('synthetic', true, 'seed_id', seed_id) AS metadata,
                NOW(),
                NOW()
            FROM seed
            ON CONFLICT (id) DO NOTHING
        $vector_insert$;
    ELSE
        EXECUTE $json_insert$
            WITH tenant_list AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS tenant_ord
                FROM tenants
            ),
            seed AS (
                SELECT
                    tl.id AS tenant_id,
                    gs.n AS seed_id,
                    md5(concat_ws('|', 'kb', tl.id, gs.n::text)) AS hash_key
                FROM tenant_list tl
                CROSS JOIN generate_series(1, 18) AS gs(n)
            )
            INSERT INTO tenant_kb_chunks (
                id,
                tenant_id,
                doc_id,
                source_uri,
                source_type,
                chunk_index,
                content,
                embedding_json,
                metadata,
                created_at,
                updated_at
            )
            SELECT
                (
                    substr(hash_key, 1, 8) || '-' ||
                    substr(hash_key, 9, 4) || '-' ||
                    substr(hash_key, 13, 4) || '-' ||
                    substr(hash_key, 17, 4) || '-' ||
                    substr(hash_key, 21, 12)
                )::uuid AS id,
                tenant_id,
                'doc-' || substr(hash_key, 1, 12) AS doc_id,
                'synthetic://' || tenant_id || '/doc/' || seed_id::text AS source_uri,
                CASE
                    WHEN seed_id <= 3 THEN 'brand_kit'
                    WHEN seed_id <= 9 THEN 'faq'
                    WHEN seed_id <= 14 THEN 'policy'
                    ELSE 'run_note'
                END AS source_type,
                seed_id AS chunk_index,
                CASE
                    WHEN seed_id <= 3 THEN 'Brand tone and positioning guidance for ' || tenant_id
                    WHEN seed_id <= 9 THEN 'Frequently asked question answer chunk ' || seed_id::text
                    WHEN seed_id <= 14 THEN 'Operational policy chunk ' || seed_id::text
                    ELSE 'Execution note chunk ' || seed_id::text
                END AS content,
                to_jsonb(ARRAY_FILL(0, ARRAY[1536])) AS embedding_json,
                jsonb_build_object('synthetic', true, 'seed_id', seed_id) AS metadata,
                NOW(),
                NOW()
            FROM seed
            ON CONFLICT (id) DO NOTHING
        $json_insert$;
    END IF;
END $$;

COMMIT;

SELECT 'tenants' AS table_name, COUNT(*)::bigint AS row_count FROM tenants
UNION ALL
SELECT 'users', COUNT(*)::bigint FROM users
UNION ALL
SELECT 'refresh_tokens', COUNT(*)::bigint FROM refresh_tokens
UNION ALL
SELECT 'runs', COUNT(*)::bigint FROM runs
UNION ALL
SELECT 'agent_state', COUNT(*)::bigint FROM agent_state
UNION ALL
SELECT 'messages', COUNT(*)::bigint FROM messages
UNION ALL
SELECT 'tickets', COUNT(*)::bigint FROM tickets
UNION ALL
SELECT 'event_outbox', COUNT(*)::bigint FROM event_outbox
UNION ALL
SELECT 'activity_logs', COUNT(*)::bigint FROM activity_logs
UNION ALL
SELECT 'human_instructions_queue', COUNT(*)::bigint FROM human_instructions_queue
UNION ALL
SELECT 'agent_intercom_queue', COUNT(*)::bigint FROM agent_intercom_queue
UNION ALL
SELECT 'tenant_kb_chunks', COUNT(*)::bigint FROM tenant_kb_chunks
ORDER BY table_name;
