-- gold/fct_agent_intercom.sql
--
-- Grain: one row per inter-agent message.
--   A "message" is a single transmission on the internal agent coordination bus,
--   sent from one agent (or the platform) to another. This is the fact table for
--   the multi-agent communication layer.
--
-- Analytics this model answers:
--   Handoff volume & rate
--     - How many times did imel hand off to kall this week / month?
--     - What share of imel runs end in a handoff vs. self-resolution? (join to fct_agent_runs on run_id)
--     - Is the handoff rate increasing as ticket volume grows, or staying flat?
--   Human escalation monitoring
--     - How many tickets were escalated to a human operator today?
--     - Which tenants have the highest escalation rates? (group by tenant_id, filter is_human_escalation)
--     - Is the escalation rate correlated with ticket priority? (join to fct_ticket_resolution on run_id → ticket_id)
--   Delivery latency & reliability
--     - What is the p50/p95 delivery latency for handoff messages?
--     - Are any messages consistently failing to deliver (delivery_latency_seconds is null = never delivered)?
--     - Is latency degrading over time on the human_interrupts channel?
--   Message volume by kind
--     - Distribution of message_kind (message, instruction, question, handoff, signal) over time.
--     - Are "thought" messages (internal agent reasoning traces) being overused?
--   Agent coordination topology
--     - Which agent pairs communicate most frequently? (group by from_agent_id, to_agent_id)
--     - Are there unexpected agent-to-agent communication patterns outside the imel → kall flow?
--
-- Join cardinality analysis:
--   int__agent_intercom_enriched  →  dim_tenants       : many-to-one on tenant_id (safe)
--   int__agent_intercom_enriched  →  agent_type_labels : many-to-one on from_agent_id
--                                                        left join × 2 (sender and receiver)
--                                                        to_agent_id may be null (broadcast)
--   No join can multiply rows. Grain is preserved.

{{ config(materialized='table') }}

with intercom as (
    select * from {{ ref('int__agent_intercom_enriched') }}
),

tenants as (
    select tenant_sk, tenant_id from {{ ref('dim_tenants') }}
),

agent_labels as (
    select agent_id, display_name as agent_display_name
    from {{ ref('agent_type_labels') }}
)

select
    -- surrogate key (inherited from silver)
    i.intercom_sk,

    -- natural key
    i.intercom_id,

    -- dimension foreign keys
    t.tenant_sk,
    i.tenant_id,

    -- run context: links this message back to the run that produced it
    -- join to fct_agent_runs on run_id to connect communication events to run outcomes
    i.run_id,

    -- agent routing (display names resolved from seed; left join preserves new agents)
    i.from_agent_id,
    from_label.agent_display_name   as from_agent_display_name,
    i.to_agent_id,
    to_label.agent_display_name     as to_agent_display_name,

    -- message classification
    i.message_kind,
    i.channel,
    i.intercom_status,
    i.priority,

    -- business intent flags (pre-computed in silver; no string matching needed here)
    i.is_handoff,
    i.is_human_escalation,

    -- measure: latency from send to delivery (null = message never delivered)
    i.delivery_latency_seconds,

    -- threading: non-null when this message is a reply to another
    i.reply_to_id,

    -- timestamps
    i.intercom_created_at,
    i.delivered_at,
    i.consumed_at,
    i.expires_at

from intercom i
-- inner join: a message with no matching tenant is a data-integrity issue upstream
inner join tenants t on i.tenant_id = t.tenant_id
-- left joins: preserve messages from/to agents not yet in the seed
left join agent_labels from_label on i.from_agent_id = from_label.agent_id
left join agent_labels to_label   on i.to_agent_id   = to_label.agent_id
