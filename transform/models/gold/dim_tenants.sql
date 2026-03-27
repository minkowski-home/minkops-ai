-- gold/dim_tenants.sql
--
-- Grain: one row per tenant (current state only).
--
-- This is the stable reference dimension that fct_agent_runs, fct_ticket_resolution,
-- and fct_agent_intercom all join to. A dimension must have exactly one row per
-- entity — joining a fact table to a dimension with duplicates causes fan-out
-- (row multiplication) that silently inflates every aggregated measure.
-- The unique test on tenant_sk in schema.yml enforces this guarantee.
--
-- Analytics this model answers (used as a join target, not queried alone):
--   Tenant segmentation across all fact tables
--     - Break down run volume, ticket SLA performance, or handoff rates by
--       tenant_plan (starter vs. pro vs. enterprise).
--     - Compare operational metrics across tenant_region for capacity planning.
--   Tenant health & churn signals
--     - Which tenants have been active longest? (order by tenant_created_at)
--     - Filter dashboards to is_enabled = false to identify recently disabled tenants
--       and correlate with their last-known run or ticket activity.
--   Account management
--     - List all active tenants on a given plan for billing or CSM review.
--     - Surface tenants with no recent runs (join to fct_agent_runs with a date filter)
--       as candidates for re-engagement.
--
-- Decision — disabled tenants:
--   Disabled tenants ARE included in this dimension. The is_enabled flag is
--   exposed as an attribute rather than used as a filter. Rationale: a disabled
--   tenant may have historical fact rows (runs, tickets) that were created while
--   the tenant was active. Filtering them out of the dimension would leave those
--   fact rows with a broken FK, making them invisible to any BI join. Downstream
--   dashboards that want to restrict to active tenants should apply
--   WHERE is_enabled = true at query time, not here.
--
-- Decision — surrogate key:
--   We generate a fresh tenant_sk here rather than reusing tenant_history_sk
--   from int__tenant_history. The history surrogate key encodes a specific
--   point-in-time snapshot (it is derived from dbt_scd_id); it is not a stable
--   identity key for the tenant entity. Fact tables need a key that says
--   "this tenant", not "this version of this tenant".

{{ config(materialized='table') }}

with current_tenants as (
    select
        tenant_id,
        tenant_name,
        tenant_plan,
        tenant_region,
        is_enabled,
        tenant_created_at
    from {{ ref('int__tenant_history') }}
    where is_current = true
)

select
    -- surrogate key: stable identity for this tenant entity
    -- derived from tenant_id, not from the SCD snapshot key
    {{ dbt_utils.generate_surrogate_key(['tenant_id']) }} as tenant_sk,

    tenant_id,
    tenant_name,
    tenant_plan,
    tenant_region,
    is_enabled,
    tenant_created_at

from current_tenants
