-- bronze/stg__agent_intercom_queue.sql
--
-- Thin staging wrapper over minkops_app.public.agent_intercom_queue.
-- Internal multi-agent messaging bus — no external side effects.
-- kind ∈ { message, instruction, question, thought, handoff, signal }
--
-- The channel='human_interrupts' lane (kind='question'|'signal') is the
-- primary path for agent→human escalation; downstream models should filter
-- on both columns together to correctly identify interrupt events.
--
-- Delivery timestamps (delivered_at, consumed_at) are preserved because
-- they are analytically meaningful for latency and throughput reporting.

with source as (

    select * from {{ source('minkops_app', 'agent_intercom_queue') }}

),

renamed as (

    select
        -- identifiers
        id              as intercom_id,
        tenant_id,
        run_id,
        reply_to        as reply_to_id,     -- self-referencing FK for threaded replies

        -- routing
        from_agent_id,
        to_agent_id,    -- NULL = broadcast within tenant/channel
        channel,        -- e.g. "human_interrupts", "ops", or NULL

        -- classification
        kind            as message_kind,
        priority,

        -- lifecycle state
        status          as intercom_status,

        -- content
        message         as message_body,
        payload         as message_payload, -- JSONB; structured context beyond free-text

        -- delivery tracking (meaningful for latency analysis)
        delivered_at,
        consumed_at,
        consumed_by,
        expires_at,

        -- timestamps
        created_at      as intercom_created_at,
        updated_at      as intercom_updated_at,

        current_timestamp as _loaded_at

    from source

)

select * from renamed
