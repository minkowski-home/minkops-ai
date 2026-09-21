-- bronze/stg__activity_logs.sql
--
-- Thin staging wrapper over minkops_dwh.public.activity_logs.
-- Append-only audit log synced from OLTP via Airbyte incremental on created_at.
--
-- Intentionally loosely coupled: tenant_id and agent_id are denormalized
-- strings, not enforced FK constraints, so log rows survive tenant/agent
-- lifecycle changes and never block deletes upstream.

with source as (

    select * from {{ source('minkops_dwh', 'activity_logs') }}

),

renamed as (

    select
        -- identifiers
        id              as log_id,
        tenant_id,
        run_id,         -- nullable; not all log events originate from a run

        -- routing
        agent_id,

        -- event
        event           as event_type,      -- canonical name: "processed_email", "escalated_ticket", etc.
        summary         as event_summary,   -- human-readable one-liner; safe for dashboards
        details         as event_details,   -- JSONB; full structured context for deep analysis

        -- timestamps
        created_at      as logged_at,       -- Airbyte incremental cursor column

        current_timestamp as _loaded_at

    from source

)

select * from renamed
