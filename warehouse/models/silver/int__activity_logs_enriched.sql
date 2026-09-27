-- silver/int__activity_logs_enriched.sql
--
-- Enriched activity log model: joins tenant context and classifies events
-- into typed boolean flags so gold models can filter without string-matching.
-- Grain: one row per activity log entry (append-only source).
--
-- Incremental cursor: logged_at (= created_at in source). Activity logs are
-- append-only by design with no updated_at column — created_at is the only
-- safe cursor and carries no late-arrival risk.

{{ config(
    materialized='incremental',
    unique_key='log_id',
    on_schema_change='fail'
) }}

with activity_logs as (
    select * from {{ ref('stg__activity_logs') }}
    {% if is_incremental() %}
        -- cursor on logged_at (timestamp), not log_id (UUID v4 — random, not time-sortable)
        where logged_at >= (select max(logged_at) from {{ this }})
    {% endif %}
),

tenants as (
    select * from {{ ref('stg__tenants') }}
),

enriched as (
    select
        -- surrogate key
        {{ dbt_utils.generate_surrogate_key(['log_id']) }} as activity_log_sk,

        -- identifiers
        a.log_id,
        a.tenant_id,
        a.run_id,

        -- tenant context
        t.tenant_name,
        t.tenant_config ->> 'region' as tenant_region,
        t.tenant_config ->> 'plan'   as tenant_plan,
        t.tenant_updated_at,

        -- routing
        a.agent_id,

        -- event classification flags
        -- event_details JSONB is intentionally not promoted to flat columns here:
        -- payload shape varies widely by event_type and may carry PII in some types.
        -- promote specific fields only after auditing each event_type for sensitivity.
        (a.event_type = 'run_failed')            as is_error_event,
        (a.event_type = 'run_progressed')        as is_run_event,
        (a.event_type = 'awaiting_human_input')  as is_escalation_event,

        a.event_type,
        a.event_summary,

        -- timestamps
        a.logged_at,
        a._loaded_at

    from activity_logs a
    join tenants t on t.tenant_id = a.tenant_id
)

select * from enriched