-- silver/int__ticket_enriched.sql
--
-- Enriched ticket model: joins tenant context, derives lifecycle booleans,
-- and computes time-based metrics. Grain: one row per ticket (current state).
--
-- Intentionally NOT incremental. Tickets are mutable entities whose status
-- transitions (open → in_progress → resolved) span days to weeks. A naive
-- incremental model would capture only latest state and silently discard
-- the transition history that SLA analysis depends on. Chapter 2.8 (snapshots)
-- addresses this correctly via SCD Type 2. Leave as view until then.

{{ config(
    materialized='view',
    on_schema_change='fail'
) }}

with base as (
    select
        -- surrogate key
        {{ dbt_utils.generate_surrogate_key(['t.ticket_id']) }} as ticket_sk,

        -- identifiers
        t.ticket_id,
        t.tenant_id,

        -- tenant context
        tn.tenant_name,
        tn.tenant_config ->> 'region'  as tenant_region,
        tn.tenant_config ->> 'plan'    as tenant_plan,
        tn.tenant_updated_at,

        -- classification
        t.ticket_status,
        t.priority,
        t.ticket_type,

        -- lifecycle booleans
        (t.ticket_status = 'resolved' or t.ticket_status = 'closed')  as is_resolved,
        (t.ticket_status = 'open')                                     as is_open,

        -- content
        t.sender_email,
        t.summary,

        -- time metrics
        -- dividing by 86400.0 (not integer 86400) forces float division,
        -- so 2d 23h = 2.958... days rather than truncating to 2
        extract(epoch from (t.ticket_updated_at - t.ticket_created_at)) / 86400.0 as ticket_open_days,

        -- timestamps
        t.ticket_created_at,
        t.ticket_updated_at

    from {{ ref('stg__tickets') }} t
    left join {{ ref('stg__tenants') }} tn on t.tenant_id = tn.tenant_id
),

enriched as (
    select *,
        ticket_open_days > 3 as is_ticket_overdue
    from base
)

select * from enriched