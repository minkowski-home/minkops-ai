-- silver/int__agent_intercom_enriched.sql
--
-- Enriched intercom model: classifies agent messages by business intent
-- and joins tenant context. Exposes escalation and handoff traffic as
-- typed boolean flags so gold models need no knowledge of channel/kind semantics.
-- Grain: one row per intercom message.

{{ config(
    materialized='incremental',
    unique_key='intercom_id',
    on_schema_change='fail'
) }}

with intercom as (
    select * from {{ ref('stg__agent_intercom_queue') }}
        {%  if is_incremental() %}
            where intercom_updated_at > ((select max(intercom_updated_at) from {{ this }}) - interval '1 hour')
        {% endif %}
),

tenants as (
    select * from {{ ref('stg__tenants') }}
),

enriched as (
    select
        -- primary key
        {{ dbt_utils.generate_surrogate_key(['intercom_id']) }} as intercom_sk,
        i.intercom_id,

        -- tenant context
        i.tenant_id,
        t.tenant_name,
        t.tenant_config ->> 'region'  as tenant_region,
        t.tenant_config ->> 'plan'    as tenant_plan,

        -- routing
        i.run_id,
        i.from_agent_id,
        i.to_agent_id,
        i.channel,
        i.reply_to_id,

        -- classification
        i.message_kind,
        i.priority,
        i.intercom_status,

        -- business intent flags
        -- both predicates required: channel alone does not imply escalation
        -- (a handoff on human_interrupts is structurally different from a question/signal)
        (i.channel = 'human_interrupts' and i.message_kind in ('question', 'signal'))
            as is_human_escalation,

        (i.message_kind = 'handoff')
            as is_handoff,

        -- latency: null when message was never delivered (expired, pending)
        case
            when i.delivered_at is not null
            then extract(epoch from (i.delivered_at - i.intercom_created_at))
        end as delivery_latency_seconds,

        -- content
        i.message_body,
        i.message_payload,

        -- timestamps
        i.intercom_created_at,
        i.intercom_updated_at,
        i.delivered_at,
        i.consumed_at,
        i.expires_at

    from intercom i
    join tenants t on i.tenant_id = t.tenant_id
)

select * from enriched
