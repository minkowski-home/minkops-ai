-- bronze/stg__runs.sql
--
-- Thin staging wrapper over minkops_dwh.public.runs.
-- A run is the atomic unit of agent work: one trigger event → one execution.
-- Status machine: queued → running → completed | failed | sleeping.
--
-- input_payload is preserved as JSONB; silver models that need specific
-- trigger fields (e.g. email_id, source_channel) should extract from it there.

with source as (

    select * from {{ source('minkops_dwh', 'runs') }}

),

renamed as (

    select
        -- identifiers
        id              as run_id,
        tenant_id,

        -- routing
        agent_id,

        -- state
        status          as run_status,

        -- trigger context
        input_payload,  -- JSONB; shape varies by agent/trigger type

        -- timestamps
        created_at      as run_created_at,
        updated_at      as run_updated_at,

        current_timestamp as _loaded_at

    from source

)

select * from renamed
