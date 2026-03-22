-- silver/int__ticket_history.sql
--
-- Silver model over snap__tickets. Exposes the full SCD Type 2 history of
-- ticket lifecycle transitions with business-friendly column names.
-- Grain: one row per ticket per lifecycle state (not one per ticket).
--
-- Primary interface: filter is_current = true for present state.
-- Point-in-time joins (e.g. "what was this ticket's status on date D?"): filter
-- where valid_from <= D and (valid_to > D or valid_to is null).
--
-- This is the correct model for SLA analysis: the duration a ticket spent
-- in each status is computable as valid_to - valid_from per row.
-- Do NOT filter to is_current here — gold models need the full transition history.

{{ config(materialized='view') }}

with snapshot as (
    select * from {{ ref('snap__tickets') }}
),

enriched as (
    select
        -- surrogate key: one unique identifier per historical record
        {{ dbt_utils.generate_surrogate_key(['dbt_scd_id']) }} as ticket_history_sk,

        -- entity identifier (stable across all versions of this ticket)
        ticket_id,
        tenant_id,

        -- lifecycle state at this point in history
        ticket_status,
        priority,
        ticket_type,

        -- lifecycle booleans derived from status (consistent with int__ticket_enriched)
        (ticket_status = 'resolved' or ticket_status = 'closed') as is_resolved,
        (ticket_status = 'open')                                  as is_open,

        -- content (informational; not in check_cols so not change-triggering)
        sender_email,
        summary,

        -- SCD metadata with business-friendly aliases
        -- valid_from / valid_to define the half-open interval [valid_from, valid_to)
        -- during which this version of the ticket was the current truth
        dbt_valid_from  as valid_from,
        dbt_valid_to    as valid_to,

        -- convenience flag: true means this is the ticket's current live state
        (dbt_valid_to is null) as is_current,

        -- retain creation timestamp for age-at-escalation calculations
        ticket_created_at,
        ticket_updated_at

    from snapshot
)

select * from enriched
