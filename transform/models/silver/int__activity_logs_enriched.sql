{{ config(
    materialized='incremental',
    unique_key = 'log_id',
    on_schema_change='fail'
) }}
-- for a purely incremental model like this one, unique key isn't that big of a concern, but we should still declare it

-- We'd still need to use the if block, because without it although dbt wont destroy previous table and recreate,
-- but still load ALL data from upstream to append
WITH activity_logs AS (
    SELECT * FROM {{ ref('stg__activity_logs') }}
   {% if is_incremental() %}
    WHERE log_id >= (SELECT max(log_id) FROM {{ this }})
   {%  endif %}
),
    tenants AS (
        SELECT * FROM {{ ref('stg__tenants') }}
    ),

    enriched AS (
        SELECT
            --identifiers
            a.log_id,
            a.tenant_id,
            a.run_id,

            -- tenant context
            t.tenant_name,
            t.tenant_config ->> 'region' AS tenant_region,
            t.tenant_config ->> 'plan' AS tenant_plan,

            -- routing
            a.agent_id,

            -- derived
            (a.event_type='run_failed') AS is_error_event,
            (a.event_type='run_progressed') AS is_run_event,
            (a.event_type='awaiting_human_input') AS is_escalation_event,
            a.event_details->>'status' AS event_status,

            a.logged_at,
            a._loaded_at
        FROM activity_logs a JOIN tenants t ON t.tenant_id = a.tenant_id
    )

SELECT *
FROM enriched