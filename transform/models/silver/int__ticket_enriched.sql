{{ config(
    materialized='view',
    on_schema_change='fail'
) }}
-- This is not incremental, because tickets table doesn't grow fast - a ticket lifecycle
-- spans days to weeks. We will handle it in SCDs.
WITH base AS (
    SELECT
        t.ticket_id,
        t.tenant_id,
        t.ticket_status,
        t.priority,
        t.ticket_created_at,
        t.ticket_updated_at,
        t.ticket_type,
        extract(EPOCH FROM (t.ticket_updated_at - t.ticket_created_at))/86400.0 AS ticket_open_days
    -- because extracting days directly would make something like 2 days 23 hours look 2 days instead of 2.95 days
    FROM {{ ref('stg__tickets') }} t
    LEFT JOIN {{ ref('stg__tenants') }} tn
    ON t.tenant_id=tn.tenant_id
),

    enriched AS (
        SELECT *,
               ticket_open_days>3 AS is_ticket_overdue
        FROM base
)

SELECT *
FROM enriched