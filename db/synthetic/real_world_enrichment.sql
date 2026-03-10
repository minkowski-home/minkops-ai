-- db/real_world_enrichment.sql
--
-- Purpose:
--   Add a large, realistic interaction dataset without modifying:
--   - db/bootstrap.sql
--   - db/schema.sql
--   - any base tables created by those files
--
-- Usage:
--   1) Run db/bootstrap.sql once
--   2) Reset/load base schema with db/schema.sql (or seed-db)
--   3) Run this script to add high-volume synthetic interaction data
--
-- Design notes:
--   - Re-runnable: drops and recreates only the tables defined here
--   - Realistic domains: CRM, product web usage, commerce, email, support
--   - Base schema remains untouched; we only reference tenants via foreign keys

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'tenants'
    ) THEN
        RAISE EXCEPTION 'Required base table "tenants" not found. Run db/schema.sql first.';
    END IF;
END $$;

DROP TABLE IF EXISTS synthetic_support_conversations;
DROP TABLE IF EXISTS synthetic_email_touchpoints;
DROP TABLE IF EXISTS synthetic_order_events;
DROP TABLE IF EXISTS synthetic_orders;
DROP TABLE IF EXISTS synthetic_web_sessions;
DROP TABLE IF EXISTS synthetic_customer_accounts;

-- Customer / account-level CRM entity.
CREATE TABLE synthetic_customer_accounts (
    customer_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_crm_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    industry TEXT NOT NULL CHECK (industry IN (
        'interior_design', 'hospitality', 'retail', 'ecommerce', 'real_estate',
        'architecture', 'manufacturing', 'consumer_goods', 'healthcare', 'technology'
    )),
    company_size_band TEXT NOT NULL CHECK (company_size_band IN (
        '1-10', '11-50', '51-200', '201-500', '501-2000'
    )),
    geography_region TEXT NOT NULL CHECK (geography_region IN (
        'ca_on', 'ca_bc', 'us_northeast', 'us_south', 'us_west',
        'uk', 'eu', 'mea', 'apac'
    )),
    acquisition_channel TEXT NOT NULL CHECK (acquisition_channel IN (
        'organic_search', 'paid_social', 'referral', 'outbound', 'partner', 'direct', 'event'
    )),
    lifecycle_stage TEXT NOT NULL CHECK (lifecycle_stage IN (
        'lead', 'trial', 'active', 'expanding', 'churned'
    )),
    first_seen_at TIMESTAMPTZ NOT NULL,
    converted_at TIMESTAMPTZ,
    churned_at TIMESTAMPTZ,
    current_mrr_usd NUMERIC(12,2) NOT NULL CHECK (current_mrr_usd >= 0),
    predicted_ltv_usd NUMERIC(12,2) NOT NULL CHECK (predicted_ltv_usd >= 0),
    health_score INT NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, external_crm_id),
    UNIQUE (tenant_id, contact_email),
    CHECK (converted_at IS NULL OR converted_at >= first_seen_at),
    CHECK (churned_at IS NULL OR churned_at >= first_seen_at)
);

CREATE INDEX idx_sca_tenant_stage ON synthetic_customer_accounts(tenant_id, lifecycle_stage);
CREATE INDEX idx_sca_region ON synthetic_customer_accounts(geography_region);
CREATE INDEX idx_sca_first_seen ON synthetic_customer_accounts(first_seen_at);

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
        md5(concat_ws('|', 'customer', tl.id, gs.n::text)) AS hash_key,
        ABS((('x' || substr(md5(concat_ws('|', 'a', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h1,
        ABS((('x' || substr(md5(concat_ws('|', 'b', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h2,
        ABS((('x' || substr(md5(concat_ws('|', 'c', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h3,
        ABS((('x' || substr(md5(concat_ws('|', 'd', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h4,
        ABS((('x' || substr(md5(concat_ws('|', 'e', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h5
    FROM generate_series(1, 9000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO synthetic_customer_accounts (
    customer_id,
    tenant_id,
    external_crm_id,
    company_name,
    contact_name,
    contact_email,
    industry,
    company_size_band,
    geography_region,
    acquisition_channel,
    lifecycle_stage,
    first_seen_at,
    converted_at,
    churned_at,
    current_mrr_usd,
    predicted_ltv_usd,
    health_score
)
SELECT
    (
        substr(hash_key, 1, 8) || '-' ||
        substr(hash_key, 9, 4) || '-' ||
        substr(hash_key, 13, 4) || '-' ||
        substr(hash_key, 17, 4) || '-' ||
        substr(hash_key, 21, 12)
    )::uuid AS customer_id,
    tenant_id,
    'CRM-' || upper(substr(hash_key, 1, 10)) AS external_crm_id,
    CASE (h1 % 10)
        WHEN 0 THEN 'Northline Studio'
        WHEN 1 THEN 'Harbor & Form'
        WHEN 2 THEN 'Aster Living Group'
        WHEN 3 THEN 'Modwell Retail'
        WHEN 4 THEN 'Stoneframe Projects'
        WHEN 5 THEN 'Quiet Oak Hospitality'
        WHEN 6 THEN 'Atlas Build Supply'
        WHEN 7 THEN 'Luma Residences'
        WHEN 8 THEN 'Cinder & Birch'
        ELSE 'Vantage Spaces'
    END || ' ' || ((seed_id % 900) + 100)::text AS company_name,
    CASE (h2 % 10)
        WHEN 0 THEN 'Avery Patel'
        WHEN 1 THEN 'Liam Chen'
        WHEN 2 THEN 'Noah Singh'
        WHEN 3 THEN 'Emma Brooks'
        WHEN 4 THEN 'Olivia Reed'
        WHEN 5 THEN 'Sophia Martin'
        WHEN 6 THEN 'Mason Clarke'
        WHEN 7 THEN 'Lucas Bennett'
        WHEN 8 THEN 'Isla Foster'
        ELSE 'Ethan Ross'
    END AS contact_name,
    'contact+' || lower(substr(hash_key, 1, 12)) || '@example.com' AS contact_email,
    CASE (h1 % 10)
        WHEN 0 THEN 'interior_design'
        WHEN 1 THEN 'hospitality'
        WHEN 2 THEN 'retail'
        WHEN 3 THEN 'ecommerce'
        WHEN 4 THEN 'real_estate'
        WHEN 5 THEN 'architecture'
        WHEN 6 THEN 'manufacturing'
        WHEN 7 THEN 'consumer_goods'
        WHEN 8 THEN 'healthcare'
        ELSE 'technology'
    END AS industry,
    CASE
        WHEN (h2 % 100) < 18 THEN '1-10'
        WHEN (h2 % 100) < 48 THEN '11-50'
        WHEN (h2 % 100) < 77 THEN '51-200'
        WHEN (h2 % 100) < 92 THEN '201-500'
        ELSE '501-2000'
    END AS company_size_band,
    CASE (h3 % 9)
        WHEN 0 THEN 'ca_on'
        WHEN 1 THEN 'ca_bc'
        WHEN 2 THEN 'us_northeast'
        WHEN 3 THEN 'us_south'
        WHEN 4 THEN 'us_west'
        WHEN 5 THEN 'uk'
        WHEN 6 THEN 'eu'
        WHEN 7 THEN 'mea'
        ELSE 'apac'
    END AS geography_region,
    CASE (h4 % 7)
        WHEN 0 THEN 'organic_search'
        WHEN 1 THEN 'paid_social'
        WHEN 2 THEN 'referral'
        WHEN 3 THEN 'outbound'
        WHEN 4 THEN 'partner'
        WHEN 5 THEN 'direct'
        ELSE 'event'
    END AS acquisition_channel,
    CASE
        WHEN (h5 % 100) < 22 THEN 'lead'
        WHEN (h5 % 100) < 38 THEN 'trial'
        WHEN (h5 % 100) < 74 THEN 'active'
        WHEN (h5 % 100) < 90 THEN 'expanding'
        ELSE 'churned'
    END AS lifecycle_stage,
    (
        CURRENT_DATE
        - ((h1 % 540)::int || ' days')::interval
        + make_interval(hours => (h2 % 24)::int, mins => (h3 % 60)::int)
    )::timestamptz AS first_seen_at,
    NULL::timestamptz AS converted_at,
    NULL::timestamptz AS churned_at,
    CASE
        WHEN (h5 % 100) < 22 THEN ROUND((h1 % 900)::numeric / 10, 2)
        WHEN (h5 % 100) < 38 THEN ROUND((150 + (h1 % 4000))::numeric / 10, 2)
        WHEN (h5 % 100) < 74 THEN ROUND((500 + (h1 % 12000))::numeric / 10, 2)
        WHEN (h5 % 100) < 90 THEN ROUND((2000 + (h1 % 30000))::numeric / 10, 2)
        ELSE ROUND((h1 % 1200)::numeric / 10, 2)
    END AS current_mrr_usd,
    ROUND((1500 + (h2 % 180000))::numeric / 10, 2) AS predicted_ltv_usd,
    (20 + (h3 % 81))::int AS health_score
FROM seed;

UPDATE synthetic_customer_accounts
SET
    converted_at = CASE
        WHEN lifecycle_stage IN ('trial', 'active', 'expanding', 'churned')
            THEN first_seen_at
                + make_interval(
                    days => (
                        2 + (
                            (('x' || substr(md5(external_crm_id || ':conv'), 1, 8))::bit(32)::bigint % 45)
                        )::int
                    )
                )
        ELSE NULL
    END,
    churned_at = CASE
        WHEN lifecycle_stage = 'churned'
            THEN first_seen_at
                + make_interval(
                    days => (
                        40 + (
                            (('x' || substr(md5(external_crm_id || ':churn'), 1, 8))::bit(32)::bigint % 180)
                        )::int
                    )
                )
        ELSE NULL
    END;

-- Session-level product and website behavior.
CREATE TABLE synthetic_web_sessions (
    session_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES synthetic_customer_accounts(customer_id) ON DELETE CASCADE,
    session_started_at TIMESTAMPTZ NOT NULL,
    session_ended_at TIMESTAMPTZ NOT NULL,
    landing_page TEXT NOT NULL CHECK (landing_page IN (
        '/', '/about', '/pricing', '/careers', '/blogs', '/orchestration',
        '/blog/lead-gen', '/blog/case-study', '/contact'
    )),
    source_channel TEXT NOT NULL CHECK (source_channel IN (
        'organic_search', 'paid_search', 'paid_social', 'email', 'direct', 'partner', 'referral'
    )),
    device_type TEXT NOT NULL CHECK (device_type IN ('desktop', 'mobile', 'tablet')),
    browser_family TEXT NOT NULL CHECK (browser_family IN ('chrome', 'safari', 'edge', 'firefox')),
    country_code TEXT NOT NULL CHECK (country_code IN ('CA', 'US', 'GB', 'DE', 'AE', 'SG', 'AU')),
    pageviews INT NOT NULL CHECK (pageviews BETWEEN 1 AND 50),
    events_count INT NOT NULL CHECK (events_count BETWEEN 1 AND 120),
    engaged_seconds INT NOT NULL CHECK (engaged_seconds BETWEEN 5 AND 7200),
    converted_to_trial BOOLEAN NOT NULL DEFAULT FALSE,
    pipeline_value_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (pipeline_value_usd >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (session_ended_at >= session_started_at)
);

CREATE INDEX idx_sws_tenant_started ON synthetic_web_sessions(tenant_id, session_started_at);
CREATE INDEX idx_sws_customer_started ON synthetic_web_sessions(customer_id, session_started_at);
CREATE INDEX idx_sws_channel ON synthetic_web_sessions(source_channel);

WITH customer_index AS (
    SELECT
        customer_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY customer_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_customer_accounts
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
        ABS((('x' || substr(md5(concat_ws('|', 'ws1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h1,
        ABS((('x' || substr(md5(concat_ws('|', 'ws2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h2,
        ABS((('x' || substr(md5(concat_ws('|', 'ws3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h3,
        ABS((('x' || substr(md5(concat_ws('|', 'ws4', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h4,
        ABS((('x' || substr(md5(concat_ws('|', 'ws5', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h5,
        md5(concat_ws('|', 'session', tl.id, gs.n::text)) AS hash_key
    FROM generate_series(1, 48000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO synthetic_web_sessions (
    session_id,
    tenant_id,
    customer_id,
    session_started_at,
    session_ended_at,
    landing_page,
    source_channel,
    device_type,
    browser_family,
    country_code,
    pageviews,
    events_count,
    engaged_seconds,
    converted_to_trial,
    pipeline_value_usd
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS session_id,
    s.tenant_id,
    ci.customer_id,
    (
        CURRENT_DATE
        - ((s.h1 % 400)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int, mins => (s.h3 % 60)::int)
    )::timestamptz AS session_started_at,
    (
        CURRENT_DATE
        - ((s.h1 % 400)::int || ' days')::interval
        + make_interval(
            hours => (s.h2 % 24)::int,
            mins => (((s.h3 % 60) + ((s.h4 % 50) + 1))::int)
        )
    )::timestamptz AS session_ended_at,
    CASE (s.h1 % 9)
        WHEN 0 THEN '/'
        WHEN 1 THEN '/about'
        WHEN 2 THEN '/pricing'
        WHEN 3 THEN '/careers'
        WHEN 4 THEN '/blogs'
        WHEN 5 THEN '/orchestration'
        WHEN 6 THEN '/blog/lead-gen'
        WHEN 7 THEN '/blog/case-study'
        ELSE '/contact'
    END AS landing_page,
    CASE (s.h2 % 7)
        WHEN 0 THEN 'organic_search'
        WHEN 1 THEN 'paid_search'
        WHEN 2 THEN 'paid_social'
        WHEN 3 THEN 'email'
        WHEN 4 THEN 'direct'
        WHEN 5 THEN 'partner'
        ELSE 'referral'
    END AS source_channel,
    CASE
        WHEN (s.h3 % 100) < 58 THEN 'desktop'
        WHEN (s.h3 % 100) < 91 THEN 'mobile'
        ELSE 'tablet'
    END AS device_type,
    CASE (s.h4 % 4)
        WHEN 0 THEN 'chrome'
        WHEN 1 THEN 'safari'
        WHEN 2 THEN 'edge'
        ELSE 'firefox'
    END AS browser_family,
    CASE (s.h5 % 7)
        WHEN 0 THEN 'CA'
        WHEN 1 THEN 'US'
        WHEN 2 THEN 'GB'
        WHEN 3 THEN 'DE'
        WHEN 4 THEN 'AE'
        WHEN 5 THEN 'SG'
        ELSE 'AU'
    END AS country_code,
    (1 + (s.h1 % 13))::int AS pageviews,
    (1 + (s.h2 % 40))::int AS events_count,
    (20 + (s.h3 % 2400))::int AS engaged_seconds,
    ((s.h4 % 100) < 14) AS converted_to_trial,
    CASE
        WHEN (s.h4 % 100) < 14 THEN ROUND((250 + (s.h5 % 90000))::numeric / 10, 2)
        ELSE ROUND((s.h5 % 2000)::numeric / 10, 2)
    END AS pipeline_value_usd
FROM seed s
JOIN customer_index ci
  ON ci.tenant_id = s.tenant_id
 AND ci.rn = 1 + ((s.seed_id * 7 + s.tenant_ord) % ci.cnt);

-- Order header/fact table representing commercial outcomes.
CREATE TABLE synthetic_orders (
    order_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES synthetic_customer_accounts(customer_id) ON DELETE CASCADE,
    source_session_id UUID REFERENCES synthetic_web_sessions(session_id) ON DELETE SET NULL,
    order_number TEXT NOT NULL,
    order_status TEXT NOT NULL CHECK (order_status IN (
        'pending', 'paid', 'fulfilled', 'delivered', 'canceled', 'returned', 'refunded'
    )),
    payment_method TEXT NOT NULL CHECK (payment_method IN (
        'card', 'wire', 'ach', 'invoice', 'shop_pay'
    )),
    currency_code TEXT NOT NULL DEFAULT 'USD' CHECK (currency_code IN ('USD', 'CAD', 'GBP', 'EUR')),
    ordered_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,
    fulfilled_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    subtotal_usd NUMERIC(12,2) NOT NULL CHECK (subtotal_usd >= 0),
    discount_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_usd >= 0),
    shipping_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (shipping_usd >= 0),
    tax_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tax_usd >= 0),
    refund_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (refund_usd >= 0),
    total_usd NUMERIC(12,2) NOT NULL CHECK (total_usd >= 0),
    margin_usd NUMERIC(12,2) NOT NULL CHECK (margin_usd >= 0),
    line_item_count INT NOT NULL CHECK (line_item_count BETWEEN 1 AND 25),
    sla_target_hours INT NOT NULL CHECK (sla_target_hours BETWEEN 24 AND 336),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, order_number)
);

CREATE INDEX idx_so_tenant_ordered ON synthetic_orders(tenant_id, ordered_at);
CREATE INDEX idx_so_customer ON synthetic_orders(customer_id);
CREATE INDEX idx_so_status ON synthetic_orders(order_status);

WITH customer_index AS (
    SELECT
        customer_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY customer_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_customer_accounts
),
session_index AS (
    SELECT
        session_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY session_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_web_sessions
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
        md5(concat_ws('|', 'order', tl.id, gs.n::text)) AS hash_key,
        ABS((('x' || substr(md5(concat_ws('|', 'o1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h1,
        ABS((('x' || substr(md5(concat_ws('|', 'o2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h2,
        ABS((('x' || substr(md5(concat_ws('|', 'o3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h3,
        ABS((('x' || substr(md5(concat_ws('|', 'o4', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h4,
        ABS((('x' || substr(md5(concat_ws('|', 'o5', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h5
    FROM generate_series(1, 18000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO synthetic_orders (
    order_id,
    tenant_id,
    customer_id,
    source_session_id,
    order_number,
    order_status,
    payment_method,
    currency_code,
    ordered_at,
    paid_at,
    fulfilled_at,
    delivered_at,
    canceled_at,
    subtotal_usd,
    discount_usd,
    shipping_usd,
    tax_usd,
    refund_usd,
    total_usd,
    margin_usd,
    line_item_count,
    sla_target_hours
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS order_id,
    s.tenant_id,
    ci.customer_id,
    si.session_id,
    'ORD-' || upper(substr(s.hash_key, 1, 12)) AS order_number,
    CASE
        WHEN (s.h1 % 100) < 6 THEN 'pending'
        WHEN (s.h1 % 100) < 19 THEN 'paid'
        WHEN (s.h1 % 100) < 54 THEN 'fulfilled'
        WHEN (s.h1 % 100) < 82 THEN 'delivered'
        WHEN (s.h1 % 100) < 89 THEN 'canceled'
        WHEN (s.h1 % 100) < 95 THEN 'returned'
        ELSE 'refunded'
    END AS order_status,
    CASE (s.h2 % 5)
        WHEN 0 THEN 'card'
        WHEN 1 THEN 'wire'
        WHEN 2 THEN 'ach'
        WHEN 3 THEN 'invoice'
        ELSE 'shop_pay'
    END AS payment_method,
    CASE (s.h3 % 4)
        WHEN 0 THEN 'USD'
        WHEN 1 THEN 'CAD'
        WHEN 2 THEN 'GBP'
        ELSE 'EUR'
    END AS currency_code,
    (
        CURRENT_DATE
        - ((s.h2 % 360)::int || ' days')::interval
        + make_interval(hours => (s.h3 % 24)::int, mins => (s.h4 % 60)::int)
    )::timestamptz AS ordered_at,
    (
        CURRENT_DATE
        - ((s.h2 % 360)::int || ' days')::interval
        + make_interval(
            hours => (s.h3 % 24)::int,
            mins => (((s.h4 % 60) + ((s.h5 % 90) + 1))::int)
        )
    )::timestamptz AS paid_at,
    (
        CURRENT_DATE
        - ((s.h2 % 360)::int || ' days')::interval
        + make_interval(
            hours => (s.h3 % 24)::int + ((s.h1 % 48) + 4)::int,
            mins => (s.h4 % 60)::int
        )
    )::timestamptz AS fulfilled_at,
    (
        CURRENT_DATE
        - ((s.h2 % 360)::int || ' days')::interval
        + make_interval(
            hours => (s.h3 % 24)::int + ((s.h1 % 120) + 24)::int,
            mins => (s.h4 % 60)::int
        )
    )::timestamptz AS delivered_at,
    (
        CURRENT_DATE
        - ((s.h2 % 360)::int || ' days')::interval
        + make_interval(
            hours => (s.h3 % 24)::int + ((s.h5 % 24) + 1)::int,
            mins => (s.h4 % 60)::int
        )
    )::timestamptz AS canceled_at,
    ROUND((1000 + (s.h3 % 180000))::numeric / 100, 2) AS subtotal_usd,
    ROUND((s.h4 % 2500)::numeric / 100, 2) AS discount_usd,
    ROUND((500 + (s.h5 % 4500))::numeric / 100, 2) AS shipping_usd,
    ROUND((300 + (s.h1 % 9000))::numeric / 100, 2) AS tax_usd,
    CASE
        WHEN (s.h1 % 100) >= 95 THEN ROUND((500 + (s.h2 % 25000))::numeric / 100, 2)
        WHEN (s.h1 % 100) >= 89 THEN ROUND((200 + (s.h2 % 12000))::numeric / 100, 2)
        ELSE 0
    END AS refund_usd,
    ROUND((1800 + (s.h3 % 210000))::numeric / 100, 2) AS total_usd,
    ROUND((700 + (s.h4 % 70000))::numeric / 100, 2) AS margin_usd,
    (1 + (s.h5 % 8))::int AS line_item_count,
    (24 + (s.h1 % 120))::int AS sla_target_hours
FROM seed s
JOIN customer_index ci
  ON ci.tenant_id = s.tenant_id
 AND ci.rn = 1 + ((s.seed_id * 5 + s.tenant_ord) % ci.cnt)
LEFT JOIN session_index si
  ON si.tenant_id = s.tenant_id
 AND si.rn = 1 + ((s.seed_id * 9 + s.tenant_ord) % si.cnt);

-- Normalize status timestamps so they are consistent with final order status.
UPDATE synthetic_orders
SET
    paid_at = CASE
        WHEN order_status = 'pending' THEN NULL
        ELSE paid_at
    END,
    fulfilled_at = CASE
        WHEN order_status IN ('fulfilled', 'delivered', 'returned', 'refunded') THEN fulfilled_at
        ELSE NULL
    END,
    delivered_at = CASE
        WHEN order_status IN ('delivered', 'returned', 'refunded') THEN delivered_at
        ELSE NULL
    END,
    canceled_at = CASE
        WHEN order_status = 'canceled' THEN canceled_at
        ELSE NULL
    END,
    total_usd = ROUND(
        GREATEST(0, subtotal_usd - discount_usd + shipping_usd + tax_usd - refund_usd),
        2
    );

-- Event stream for orders, useful for sequence analysis and funnel SQL.
CREATE TABLE synthetic_order_events (
    order_event_id BIGSERIAL PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES synthetic_orders(order_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_seq INT NOT NULL CHECK (event_seq BETWEEN 1 AND 10),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'created', 'payment_authorized', 'packed', 'shipped',
        'delivered', 'canceled', 'return_requested', 'refunded'
    )),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('customer', 'agent', 'system', 'warehouse', 'carrier')),
    event_at TIMESTAMPTZ NOT NULL,
    event_value_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (event_value_usd >= 0),
    notes TEXT,
    UNIQUE (order_id, event_seq)
);

CREATE INDEX idx_soe_order_time ON synthetic_order_events(order_id, event_at);
CREATE INDEX idx_soe_tenant_type ON synthetic_order_events(tenant_id, event_type);

INSERT INTO synthetic_order_events (
    order_id,
    tenant_id,
    event_seq,
    event_type,
    actor_type,
    event_at,
    event_value_usd,
    notes
)
SELECT
    o.order_id,
    o.tenant_id,
    e.event_seq,
    e.event_type,
    e.actor_type,
    e.event_at,
    e.event_value_usd,
    e.notes
FROM synthetic_orders o
CROSS JOIN LATERAL (
    SELECT
        1 AS event_seq,
        'created'::text AS event_type,
        'customer'::text AS actor_type,
        o.ordered_at AS event_at,
        o.total_usd AS event_value_usd,
        'Order submitted from web or outbound workflow.'::text AS notes
    UNION ALL
    SELECT
        2,
        'payment_authorized',
        'system',
        o.paid_at,
        o.total_usd,
        'Payment authorization completed.'
    WHERE o.paid_at IS NOT NULL
    UNION ALL
    SELECT
        3,
        'packed',
        'warehouse',
        o.fulfilled_at - INTERVAL '4 hours',
        o.margin_usd,
        'Warehouse prepared line items for dispatch.'
    WHERE o.fulfilled_at IS NOT NULL
    UNION ALL
    SELECT
        4,
        'shipped',
        'carrier',
        o.fulfilled_at,
        o.shipping_usd,
        'Shipment handed off to final-mile carrier.'
    WHERE o.fulfilled_at IS NOT NULL
    UNION ALL
    SELECT
        5,
        'delivered',
        'carrier',
        o.delivered_at,
        o.total_usd,
        'Delivery confirmed.'
    WHERE o.delivered_at IS NOT NULL
    UNION ALL
    SELECT
        5,
        'canceled',
        'agent',
        o.canceled_at,
        o.total_usd,
        'Order canceled before fulfillment.'
    WHERE o.canceled_at IS NOT NULL
    UNION ALL
    SELECT
        6,
        'return_requested',
        'customer',
        o.delivered_at + INTERVAL '2 days',
        o.refund_usd,
        'Customer initiated return request.'
    WHERE o.order_status IN ('returned', 'refunded') AND o.delivered_at IS NOT NULL
    UNION ALL
    SELECT
        7,
        'refunded',
        'system',
        o.delivered_at + INTERVAL '4 days',
        o.refund_usd,
        'Refund settled after review.'
    WHERE o.order_status = 'refunded' AND o.delivered_at IS NOT NULL
) e;

-- Email touchpoints across marketing, sales, support, and ops.
CREATE TABLE synthetic_email_touchpoints (
    touchpoint_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES synthetic_customer_accounts(customer_id) ON DELETE CASCADE,
    related_order_id UUID REFERENCES synthetic_orders(order_id) ON DELETE SET NULL,
    direction TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    mailbox_type TEXT NOT NULL CHECK (mailbox_type IN ('marketing', 'sales', 'support', 'ops')),
    campaign_kind TEXT NOT NULL CHECK (campaign_kind IN (
        'onboarding', 'nurture', 'winback', 'support_followup',
        'invoice', 'lead_outreach', 'product_update'
    )),
    provider TEXT NOT NULL CHECK (provider IN ('ses', 'sendgrid', 'gmail', 'outlook')),
    subject_template TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    delivery_status TEXT NOT NULL CHECK (delivery_status IN (
        'sent', 'delivered', 'opened', 'clicked', 'replied', 'bounced', 'spam_report', 'unsubscribed'
    )),
    open_count INT NOT NULL DEFAULT 0 CHECK (open_count BETWEEN 0 AND 20),
    click_count INT NOT NULL DEFAULT 0 CHECK (click_count BETWEEN 0 AND 20),
    reply_count INT NOT NULL DEFAULT 0 CHECK (reply_count BETWEEN 0 AND 10),
    is_unsubscribed BOOLEAN NOT NULL DEFAULT FALSE,
    handling_time_ms INT NOT NULL CHECK (handling_time_ms BETWEEN 10 AND 180000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_set_tenant_sent ON synthetic_email_touchpoints(tenant_id, sent_at);
CREATE INDEX idx_set_customer_sent ON synthetic_email_touchpoints(customer_id, sent_at);
CREATE INDEX idx_set_status ON synthetic_email_touchpoints(delivery_status);

WITH customer_index AS (
    SELECT
        customer_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY customer_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_customer_accounts
),
order_index AS (
    SELECT
        order_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY order_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_orders
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
        ABS((('x' || substr(md5(concat_ws('|', 'm1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h1,
        ABS((('x' || substr(md5(concat_ws('|', 'm2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h2,
        ABS((('x' || substr(md5(concat_ws('|', 'm3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h3,
        ABS((('x' || substr(md5(concat_ws('|', 'm4', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h4
    FROM generate_series(1, 62000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO synthetic_email_touchpoints (
    tenant_id,
    customer_id,
    related_order_id,
    direction,
    mailbox_type,
    campaign_kind,
    provider,
    subject_template,
    sent_at,
    delivery_status,
    open_count,
    click_count,
    reply_count,
    is_unsubscribed,
    handling_time_ms
)
SELECT
    s.tenant_id,
    ci.customer_id,
    oi.order_id,
    CASE WHEN (s.h1 % 100) < 78 THEN 'outbound' ELSE 'inbound' END AS direction,
    CASE (s.h2 % 4)
        WHEN 0 THEN 'marketing'
        WHEN 1 THEN 'sales'
        WHEN 2 THEN 'support'
        ELSE 'ops'
    END AS mailbox_type,
    CASE (s.h3 % 7)
        WHEN 0 THEN 'onboarding'
        WHEN 1 THEN 'nurture'
        WHEN 2 THEN 'winback'
        WHEN 3 THEN 'support_followup'
        WHEN 4 THEN 'invoice'
        WHEN 5 THEN 'lead_outreach'
        ELSE 'product_update'
    END AS campaign_kind,
    CASE (s.h4 % 4)
        WHEN 0 THEN 'ses'
        WHEN 1 THEN 'sendgrid'
        WHEN 2 THEN 'gmail'
        ELSE 'outlook'
    END AS provider,
    CASE (s.h3 % 7)
        WHEN 0 THEN 'welcome_sequence_v2'
        WHEN 1 THEN 'pipeline_check_in'
        WHEN 2 THEN 'winback_offer_q3'
        WHEN 3 THEN 'ticket_followup_resolution'
        WHEN 4 THEN 'invoice_receipt'
        WHEN 5 THEN 'lead_outreach_personalized'
        ELSE 'product_release_notes'
    END AS subject_template,
    (
        CURRENT_DATE
        - ((s.h1 % 365)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int, mins => (s.h3 % 60)::int)
    )::timestamptz AS sent_at,
    CASE
        WHEN (s.h4 % 100) < 8 THEN 'bounced'
        WHEN (s.h4 % 100) < 11 THEN 'spam_report'
        WHEN (s.h4 % 100) < 18 THEN 'unsubscribed'
        WHEN (s.h4 % 100) < 38 THEN 'delivered'
        WHEN (s.h4 % 100) < 63 THEN 'opened'
        WHEN (s.h4 % 100) < 79 THEN 'clicked'
        WHEN (s.h4 % 100) < 91 THEN 'replied'
        ELSE 'sent'
    END AS delivery_status,
    CASE
        WHEN (s.h4 % 100) >= 38 THEN (s.h1 % 6)::int
        ELSE 0
    END AS open_count,
    CASE
        WHEN (s.h4 % 100) >= 63 THEN (s.h2 % 4)::int
        ELSE 0
    END AS click_count,
    CASE
        WHEN (s.h4 % 100) >= 79 THEN 1 + (s.h3 % 2)::int
        ELSE 0
    END AS reply_count,
    ((s.h4 % 100) BETWEEN 11 AND 17) AS is_unsubscribed,
    (30 + (s.h1 % 25000))::int AS handling_time_ms
FROM seed s
JOIN customer_index ci
  ON ci.tenant_id = s.tenant_id
 AND ci.rn = 1 + ((s.seed_id * 13 + s.tenant_ord) % ci.cnt)
LEFT JOIN order_index oi
  ON oi.tenant_id = s.tenant_id
 AND oi.rn = 1 + ((s.seed_id * 5 + s.tenant_ord) % oi.cnt);

-- Support interactions that look like operational work, not just analytics facts.
CREATE TABLE synthetic_support_conversations (
    conversation_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES synthetic_customer_accounts(customer_id) ON DELETE CASCADE,
    related_order_id UUID REFERENCES synthetic_orders(order_id) ON DELETE SET NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'phone', 'chat', 'social')),
    issue_type TEXT NOT NULL CHECK (issue_type IN (
        'delivery_delay', 'billing_question', 'cancel_request', 'product_question',
        'refund_request', 'account_access', 'damaged_item', 'general_feedback'
    )),
    queue_name TEXT NOT NULL CHECK (queue_name IN ('support_l1', 'support_l2', 'retention', 'operations')),
    status TEXT NOT NULL CHECK (status IN ('open', 'resolved', 'waiting_customer', 'escalated', 'closed')),
    opened_at TIMESTAMPTZ NOT NULL,
    first_response_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    message_count INT NOT NULL CHECK (message_count BETWEEN 1 AND 60),
    agent_handoffs INT NOT NULL CHECK (agent_handoffs BETWEEN 0 AND 12),
    resolution_sla_minutes INT NOT NULL CHECK (resolution_sla_minutes BETWEEN 15 AND 10080),
    csat_score INT CHECK (csat_score BETWEEN 1 AND 5),
    refund_issued_usd NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (refund_issued_usd >= 0),
    escalated_to_human BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (first_response_at IS NULL OR first_response_at >= opened_at),
    CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
);

CREATE INDEX idx_ssc_tenant_opened ON synthetic_support_conversations(tenant_id, opened_at);
CREATE INDEX idx_ssc_status ON synthetic_support_conversations(status);
CREATE INDEX idx_ssc_issue_type ON synthetic_support_conversations(issue_type);

WITH customer_index AS (
    SELECT
        customer_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY customer_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_customer_accounts
),
order_index AS (
    SELECT
        order_id,
        tenant_id,
        ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY order_id) AS rn,
        COUNT(*) OVER (PARTITION BY tenant_id) AS cnt
    FROM synthetic_orders
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
        md5(concat_ws('|', 'conv', tl.id, gs.n::text)) AS hash_key,
        ABS((('x' || substr(md5(concat_ws('|', 'c1', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h1,
        ABS((('x' || substr(md5(concat_ws('|', 'c2', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h2,
        ABS((('x' || substr(md5(concat_ws('|', 'c3', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h3,
        ABS((('x' || substr(md5(concat_ws('|', 'c4', tl.id, gs.n::text)), 1, 8))::bit(32)::bigint)) AS h4
    FROM generate_series(1, 14000) AS gs(n)
    CROSS JOIN tenant_meta tm
    JOIN tenant_list tl
      ON tl.tenant_ord = 1 + ((gs.n - 1) % tm.tenant_count)
)
INSERT INTO synthetic_support_conversations (
    conversation_id,
    tenant_id,
    customer_id,
    related_order_id,
    channel,
    issue_type,
    queue_name,
    status,
    opened_at,
    first_response_at,
    resolved_at,
    message_count,
    agent_handoffs,
    resolution_sla_minutes,
    csat_score,
    refund_issued_usd,
    escalated_to_human
)
SELECT
    (
        substr(s.hash_key, 1, 8) || '-' ||
        substr(s.hash_key, 9, 4) || '-' ||
        substr(s.hash_key, 13, 4) || '-' ||
        substr(s.hash_key, 17, 4) || '-' ||
        substr(s.hash_key, 21, 12)
    )::uuid AS conversation_id,
    s.tenant_id,
    ci.customer_id,
    oi.order_id,
    CASE (s.h1 % 4)
        WHEN 0 THEN 'email'
        WHEN 1 THEN 'phone'
        WHEN 2 THEN 'chat'
        ELSE 'social'
    END AS channel,
    CASE (s.h2 % 8)
        WHEN 0 THEN 'delivery_delay'
        WHEN 1 THEN 'billing_question'
        WHEN 2 THEN 'cancel_request'
        WHEN 3 THEN 'product_question'
        WHEN 4 THEN 'refund_request'
        WHEN 5 THEN 'account_access'
        WHEN 6 THEN 'damaged_item'
        ELSE 'general_feedback'
    END AS issue_type,
    CASE
        WHEN (s.h3 % 100) < 55 THEN 'support_l1'
        WHEN (s.h3 % 100) < 82 THEN 'support_l2'
        WHEN (s.h3 % 100) < 92 THEN 'retention'
        ELSE 'operations'
    END AS queue_name,
    CASE
        WHEN (s.h4 % 100) < 10 THEN 'open'
        WHEN (s.h4 % 100) < 63 THEN 'resolved'
        WHEN (s.h4 % 100) < 78 THEN 'waiting_customer'
        WHEN (s.h4 % 100) < 91 THEN 'escalated'
        ELSE 'closed'
    END AS status,
    (
        CURRENT_DATE
        - ((s.h1 % 300)::int || ' days')::interval
        + make_interval(hours => (s.h2 % 24)::int, mins => (s.h3 % 60)::int)
    )::timestamptz AS opened_at,
    (
        CURRENT_DATE
        - ((s.h1 % 300)::int || ' days')::interval
        + make_interval(
            hours => (s.h2 % 24)::int,
            mins => (((s.h3 % 60) + ((s.h4 % 50) + 1))::int)
        )
    )::timestamptz AS first_response_at,
    (
        CURRENT_DATE
        - ((s.h1 % 300)::int || ' days')::interval
        + make_interval(
            hours => (s.h2 % 24)::int + ((s.h4 % 144) + 2)::int,
            mins => (s.h3 % 60)::int
        )
    )::timestamptz AS resolved_at,
    (1 + (s.h1 % 20))::int AS message_count,
    (s.h2 % 5)::int AS agent_handoffs,
    (30 + (s.h3 % 2880))::int AS resolution_sla_minutes,
    CASE
        WHEN (s.h4 % 100) < 14 THEN NULL
        ELSE 1 + (s.h2 % 5)::int
    END AS csat_score,
    CASE
        WHEN (s.h2 % 100) < 19 THEN ROUND((200 + (s.h3 % 25000))::numeric / 100, 2)
        ELSE 0
    END AS refund_issued_usd,
    ((s.h4 % 100) >= 78) AS escalated_to_human
FROM seed s
JOIN customer_index ci
  ON ci.tenant_id = s.tenant_id
 AND ci.rn = 1 + ((s.seed_id * 3 + s.tenant_ord) % ci.cnt)
LEFT JOIN order_index oi
  ON oi.tenant_id = s.tenant_id
 AND oi.rn = 1 + ((s.seed_id * 11 + s.tenant_ord) % oi.cnt);

-- Normalize response/resolution timestamps based on final status semantics.
UPDATE synthetic_support_conversations
SET
    first_response_at = CASE
        WHEN status = 'open' THEN NULL
        ELSE first_response_at
    END,
    resolved_at = CASE
        WHEN status IN ('resolved', 'closed') THEN resolved_at
        ELSE NULL
    END;

COMMIT;

-- Row-count summary for quick validation.
SELECT 'synthetic_customer_accounts' AS table_name, COUNT(*)::bigint AS row_count FROM synthetic_customer_accounts
UNION ALL
SELECT 'synthetic_web_sessions', COUNT(*)::bigint FROM synthetic_web_sessions
UNION ALL
SELECT 'synthetic_orders', COUNT(*)::bigint FROM synthetic_orders
UNION ALL
SELECT 'synthetic_order_events', COUNT(*)::bigint FROM synthetic_order_events
UNION ALL
SELECT 'synthetic_email_touchpoints', COUNT(*)::bigint FROM synthetic_email_touchpoints
UNION ALL
SELECT 'synthetic_support_conversations', COUNT(*)::bigint FROM synthetic_support_conversations
ORDER BY table_name;
