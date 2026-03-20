-- bronze/stg__tickets.sql
--
-- Thin staging wrapper over minkops_dwh.public.tickets.
-- Tickets are support cases created by agents or humans from inbound email.
-- Status lifecycle: open → in_progress → resolved → closed.
--
-- raw_email is intentionally excluded: it may contain PII and its bulk
-- is better handled in a purpose-built, access-controlled model.

with source as (

    select * from {{ source('minkops_dwh', 'tickets') }}

),

renamed as (

    select
        -- identifiers
        id              as ticket_id,
        tenant_id,
        email_id,       -- link back to source email (not FK-constrained in OLTP)

        -- classification
        ticket_type,
        priority,
        status          as ticket_status,

        -- content
        sender_email,
        summary,        -- agent-generated; safe for dashboards and reporting

        -- raw_email excluded (PII; use a restricted silver model if needed)

        -- timestamps
        created_at      as ticket_created_at,
        updated_at      as ticket_updated_at,

        current_timestamp as _loaded_at

    from source

)

select * from renamed
