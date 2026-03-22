-- bronze/stg__tenants.sql
--
-- Thin staging wrapper over minkops_dwh.public.tenants.
-- Renames the generic `id` PK and preserves the `enabled` flag intact —
-- downstream models use it to filter disabled tenants rather than relying
-- on hard-deletes that never happen in this table.

with source as (

    select * from {{ source('minkops_dwh', 'tenants') }}

),

renamed as (

    select
        -- identifiers
        id                  as tenant_id,

        -- attributes
        name                as tenant_name,
        config              as tenant_config,       -- JSONB; plan tier, region, API keys
        enabled             as is_enabled,

        -- timestamps
        created_at          as tenant_created_at,
        updated_at          as tenant_updated_at,

        current_timestamp   as _loaded_at

    from source

)

select * from renamed
