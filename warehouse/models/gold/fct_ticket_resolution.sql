-- gold/fct_ticket_resolution.sql
--
-- Analytics this model answers:
--   SLA compliance
--     - What percentage of tickets were resolved within their priority SLA target?
--       (filter is_current = false, is_resolved = true, group by is_sla_breached)
--     - Which priority tier has the highest breach rate this month?
--     - Which tenants are consistently breaching SLA? (group by tenant_id, is_sla_breached)
--   Live breach monitoring
--     - How many tickets are currently breaching their SLA right now?
--       (filter is_current = true, is_sla_breached = true)
--     - How long past the SLA threshold are the worst offenders?
--       (time_in_status_hours - target_resolution_hours where is_current and is_sla_breached)
--   Status funnel & bottleneck analysis
--     - What is the average time tickets spend in each status?
--       (group by ticket_status, avg(time_in_status_hours))
--     - Are tickets getting stuck in in_progress? Is that status taking longer than open?
--     - How does time-in-status differ across ticket_type or priority?
--   Ticket volume & backlog
--     - How many tickets are open right now, by priority? (filter is_current, is_open)
--     - What is the weekly ticket creation trend? (group by date_trunc('week', ticket_created_at))
--     - What share of tickets close without ever entering in_progress (direct open → resolved)?
--   Historical lifecycle reconstruction
--     - For a given ticket_id, show the full status history in order of valid_from.
--     - How long did ticket X spend in each state before resolution?
--
-- Grain: one row per ticket per lifecycle state transition.
--   A ticket that moves open → in_progress → resolved produces three rows here,
--   one for each status it occupied. This is the correct grain for SLA analysis:
--   time_in_status_hours is only computable from the SCD history, not from the
--   current-state view in int__ticket_enriched.
--
-- Source: int__ticket_history (SCD Type 2 wrapper over snap__tickets).
--   Do NOT substitute int__ticket_enriched — it holds only the current state and
--   would collapse all transition history into a single row per ticket.
--
-- Join cardinality analysis:
--   int__ticket_history  →  dim_tenants          : many-to-one on tenant_id (safe)
--   int__ticket_history  →  ticket_priority_sla  : many-to-one on priority
--                                                  left join: null priority tickets
--                                                  get null SLA target and
--                                                  is_sla_breached = null (not false),
--                                                  which is honest — we cannot
--                                                  evaluate SLA without a priority.
--   Neither join can multiply rows. Grain is preserved.
--
-- time_in_status_hours:
--   For closed transitions (valid_to IS NOT NULL): exact elapsed hours in that state.
--   For the current active state (valid_to IS NULL): hours elapsed since valid_from
--   up to now(). This is critical — a null here would make in-flight tickets
--   invisible in "time currently spent in status" dashboards.
--   Formula: extract(epoch from (coalesce(valid_to, now()) - valid_from)) / 3600.0
--
-- is_sla_breached — definition and edge cases:
--   Measures total ticket lifetime (ticket_created_at to the end of this transition,
--   or now() for the active state) against the priority SLA target.
--   This answers the question: "by the time this status ended (or as of now),
--   had the ticket already exceeded its SLA budget?"
--
--   Resolved/closed tickets: valid_to is the exact moment the terminal status was
--   entered; the breach flag is a historical fact that will never change.
--
--   Current (is_current = true) tickets: valid_to is null, so coalesce(..., now())
--   makes the flag a live indicator that flips from false to true at the SLA
--   threshold. A BI dashboard filtering to is_current = true therefore shows all
--   tickets currently in breach in real time (within the gold table refresh cadence).

{{ config(materialized='table') }}

with ticket_history as (
    select * from {{ ref('int__ticket_history') }}
),

tenants as (
    select tenant_sk, tenant_id from {{ ref('dim_tenants') }}
),

sla as (
    select priority, target_resolution_hours
    from {{ ref('ticket_priority_sla') }}
)

select
    -- surrogate key: unique per transition row (inherited from silver SCD model)
    th.ticket_history_sk,

    -- natural key
    th.ticket_id,

    -- dimension foreign keys
    t.tenant_sk,
    th.tenant_id,

    -- ticket state during this transition
    th.ticket_status,
    th.priority,
    th.ticket_type,

    -- lifecycle booleans (consistent with silver definitions)
    th.is_resolved,
    th.is_open,
    th.is_current,

    -- SCD interval
    th.valid_from,
    th.valid_to,

    -- measure: hours this ticket spent in this specific status
    -- coalesce(valid_to, now()) ensures in-flight transitions are never null
    extract(epoch from (coalesce(th.valid_to, now()) - th.valid_from)) / 3600.0
        as time_in_status_hours,

    -- SLA reference value (carried through for BI transparency)
    sla.target_resolution_hours,

    -- SLA breach flag: true when total ticket age at the end of this transition
    -- (or now, for the active state) exceeds the priority target.
    -- null when priority is null (no SLA target can be evaluated).
    case
        when sla.target_resolution_hours is null then null
        else (
            extract(epoch from (coalesce(th.valid_to, now()) - th.ticket_created_at))
            / 3600.0
        ) > sla.target_resolution_hours
    end as is_sla_breached,

    -- ticket creation timestamp (anchor for total-lifetime calculations)
    th.ticket_created_at

from ticket_history th
-- inner join: a ticket row with no tenant is a data-integrity issue upstream
inner join tenants t on th.tenant_id = t.tenant_id
-- left join: preserve tickets with null or unrecognised priority
left join sla on th.priority = sla.priority
