-- silver/int__run_enriched.sql
--
-- Enriched run model: joins tenant context, derives duration and terminal flag,
-- and promotes selected input_payload fields to typed columns.
-- Grain: one row per run.

{{ config(
    materialized='incremental',
    unique_key='run_id',
    on_schema_change='fail'
) }}

with runs as (
    select * from {{ ref('stg__runs') }}
        {% if is_incremental() %}
            where run_updated_at >= ((select max(run_updated_at) from {{ this }}) - interval '3 hours')
        {% endif %}
),

     tenants as (
         select * from {{ ref('stg__tenants') }}
     ),

     enriched as (
         select
             -- primary key
             r.run_id,

             -- tenant context
             r.tenant_id,
             t.tenant_name,
             t.tenant_config ->> 'region'    as tenant_region,
             t.tenant_config ->> 'plan'      as tenant_plan,

             -- routing
            r.agent_id,

             -- state
            r.run_status,
            r.run_status in ('completed', 'failed')  as is_terminal,

             -- promoted payload fields (nullable: shape varies by agent/trigger type)
            r.input_payload ->> 'priority'          as trigger_priority,
            r.input_payload ->> 'trigger_kind'      as trigger_kind,

             -- derived metrics
            case
            when r.run_status in ('completed', 'failed')
            then extract(epoch from (r.run_updated_at - r.run_created_at))
            end                                      as run_duration_seconds,

            -- timestamps
            r.run_created_at,
            r.run_updated_at

        from runs r
        join tenants t on r.tenant_id = t.tenant_id
)

select * from enriched