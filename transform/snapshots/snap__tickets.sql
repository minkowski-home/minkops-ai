-- snapshots/snap__tickets.sql
--
-- SCD Type 2 snapshot of the tickets table.
--
-- Strategy: check, on ['ticket_status', 'priority', 'ticket_type'].
--
-- Tickets have updated_at, so timestamp strategy is technically available.
-- However, the application touches ticket rows for changes that are not
-- analytically meaningful — e.g., updating the agent-generated summary field
-- or internal metadata. With timestamp strategy, every such touch would create
-- a spurious new snapshot record, inflating the history table and making
-- point-in-time joins noisier.
--
-- check strategy constrains change detection to the three columns that
-- represent genuine lifecycle transitions: status progression, priority
-- escalation, and ticket reclassification. A new snapshot row is only
-- created when one of these actually changes — which is the correct
-- semantics for SLA and lifecycle analysis.
--
-- sender_email and summary are intentionally excluded from check_cols:
-- sender_email never changes post-creation, and summary updates are
-- agent cosmetic edits that do not represent a lifecycle event.

{% snapshot snap__tickets %}

{{
    config(
        target_schema='snapshots',
        strategy='check',
        unique_key='ticket_id',
        check_cols=['ticket_status', 'priority', 'ticket_type'],
        invalidate_hard_deletes=True
    )
}}

select * from {{ ref('stg__tickets') }}

{% endsnapshot %}
