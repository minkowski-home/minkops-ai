-- gold/fct_agent_runs.sql
--
-- Analytics this model answers:
--   Run volume & throughput
--     - How many runs did each agent complete today / this week?
--     - What is the daily run volume trend over the last 30 days?
--     - Which tenants are generating the most agent work?
--   Agent performance
--     - What is the p50/p95 run duration per agent? (run_duration_seconds where is_terminal)
--     - What fraction of runs fail vs. complete? (group by run_status or is_terminal)
--     - Is run duration increasing over time, suggesting degradation?
--   Trigger analysis
--     - What trigger_kind events are driving the most runs?
--     - Are high trigger_priority runs completing faster than low-priority ones?
--   Capacity & load
--     - How many concurrent runs were active at any given hour? (count where not is_terminal)
--     - Which tenants have the highest failure rates?
--   Cross-model joins
--     - Join to fct_agent_intercom on run_id to see which runs produced a handoff.
--     - Join to fct_ticket_resolution on run_id (via tickets) to correlate run outcomes
--       with ticket resolution time.
--
-- Grain: one row per agent run.
--   A "run" is a single, atomic execution of one agent triggered by one event.
--   The runs table is the primary unit of agent work — grain confirmed by the
--   unique_key='run_id' contract on int__run_enriched.
--
-- Join cardinality analysis:
--   int__run_enriched  →  dim_tenants       : many-to-one on tenant_id
--                                             (each run belongs to exactly one tenant;
--                                              dim_tenants has unique tenant_sk per tenant)
--   int__run_enriched  →  agent_type_labels  : many-to-one on agent_id
--                                             (seed has two rows, one per agent type;
--                                              left join preserves runs if a new agent
--                                              is deployed before the seed is updated)
--   Both joins preserve grain: no run can be multiplied.
--
-- Decision — tenant context from silver vs. direct join to dim_tenants:
--   int__run_enriched already promotes tenant_name, tenant_plan, and tenant_region
--   by joining stg__tenants at silver build time. We do NOT re-read those columns
--   here; we take them from the silver model to avoid touching the same source twice
--   in the same pipeline run.
--   However, we DO join to dim_tenants to obtain tenant_sk. This foreign key is
--   essential: it is what allows BI tools (Metabase, Looker, Tableau) to navigate
--   from this fact table to the tenant dimension without a manual SQL join. The join
--   is cheap because dim_tenants is a small, fully-materialized gold table.

{{ config(materialized='table') }}

with runs as (
    select * from {{ ref('int__run_enriched') }}
),

tenants as (
    -- join only for the surrogate key; all tenant attributes come from silver
    select tenant_sk, tenant_id from {{ ref('dim_tenants') }}
),

agent_labels as (
    select agent_id, display_name as agent_display_name
    from {{ ref('agent_type_labels') }}
)

select
    -- surrogate key (inherited from silver — already stable and unique per run)
    r.run_sk,

    -- natural key
    r.run_id,

    -- dimension foreign keys
    t.tenant_sk,         -- FK to dim_tenants; enables BI tool relationships
    r.tenant_id,         -- retained as a readable filter column

    -- agent dimension (denormalised display name; agent_type_labels is a tiny seed)
    r.agent_id,
    a.agent_display_name,

    -- run lifecycle
    r.run_status,
    r.is_terminal,

    -- measures
    r.run_duration_seconds,

    -- trigger context (nullable: varies by agent and trigger type)
    r.trigger_kind,
    r.trigger_priority,

    -- timestamps
    r.run_created_at,
    r.run_updated_at

from runs r
-- inner join: a run with no matching tenant is a data-integrity issue upstream;
-- surfacing it as a null row here would pollute tenant-scoped aggregations
inner join tenants t on r.tenant_id = t.tenant_id
-- left join: preserve runs even if agent_id has no label yet (new agent deployment)
left join agent_labels a on r.agent_id = a.agent_id
