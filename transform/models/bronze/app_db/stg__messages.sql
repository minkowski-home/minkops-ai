-- bronze/stg__messages.sql
--
-- Thin staging wrapper over minkops_app.public.messages.
-- Full conversation history keyed to a run.
-- role ∈ { user, assistant, system, tool }.
--
-- content is intentionally excluded at the bronze layer: message text
-- frequently contains PII (customer names, emails, order details). Any
-- model that needs content must be built in silver with explicit masking
-- or access controls applied there.

with source as (

    select * from {{ source('minkops_app', 'messages') }}

),

renamed as (

    select
        -- identifiers
        id              as message_id,
        run_id,
        tenant_id,

        -- attributes
        role            as message_role,

        -- content excluded — PII risk; handle in a restricted silver model
        meta            as message_meta,    -- JSONB: model, token counts, tool names, etc.

        -- timestamps
        created_at      as message_created_at,

        current_timestamp as _loaded_at

    from source

)

select * from renamed
