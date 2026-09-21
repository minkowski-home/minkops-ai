-- silver/int__tenant_history.sql
--
-- Silver model over snap__tenants. Exposes the full SCD Type 2 history of
-- tenant configuration changes with business-friendly column names.
-- Grain: one row per tenant per historical state (not one per tenant).
--
-- Primary interface: filter is_current = true for present state.
-- Point-in-time joins (e.g. "what was tenant X's plan on date D?"): filter
-- where valid_from <= D and (valid_to > D or valid_to is null).
-- Do NOT filter to is_current here — gold models need the full history.

{{ config(materialized='view') }}

with snapshot as (
    select * from {{ ref('snap__tenants') }}
),

enriched as (
    select
        -- surrogate key: one unique identifier per historical record
        -- generated from dbt_scd_id which dbt guarantees is unique per snapshot row
        {{ dbt_utils.generate_surrogate_key(['dbt_scd_id']) }} as tenant_history_sk,

        -- entity identifier (stable across all versions of this tenant)
        tenant_id,
        tenant_name,

        -- promoted config fields — no downstream model should touch JSONB directly
        tenant_config,
        tenant_config ->> 'plan'   as tenant_plan,
        tenant_config ->> 'region' as tenant_region,

        -- enabled state
        is_enabled,

        -- SCD metadata with business-friendly aliases
        -- valid_from / valid_to define the half-open interval [valid_from, valid_to)
        -- during which this version of the row was the current truth
        dbt_valid_from  as valid_from,
        dbt_valid_to    as valid_to,

        -- convenience flag: true means this is the tenant's current live state
        (dbt_valid_to is null) as is_current,

        -- retain the creation timestamp for tenure calculations
        tenant_created_at

    from snapshot
)

select * from enriched
