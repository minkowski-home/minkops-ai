-- snapshots/snap__tenants.sql
--
-- SCD Type 2 snapshot of the tenants table.
--
-- Strategy: timestamp, using tenant_updated_at.
--
-- tenants carries updated_at maintained by the set_updated_at trigger on every
-- row mutation (see 01_schema.sql). This makes timestamp the correct strategy:
-- cheaper than check (single column compare vs full-row hash) and more precise
-- (creates a new snapshot row exactly when a mutation happens, not on every run).
--
-- All mutable columns are captured automatically — no explicit check_cols needed.
-- tenant_id is the natural PK and never changes.
-- tenant_created_at is immutable by definition.
--
-- tenant_name IS tracked: renames are rare but analytically meaningful.
-- Knowing what name a tenant operated under during a given period matters
-- for historical reporting even if the underlying entity is the same.

{% snapshot snap__tenants %}

{{
    config(
        target_schema='snapshots',
        strategy='timestamp',
        unique_key='tenant_id',
        updated_at='tenant_updated_at',
        invalidate_hard_deletes=True
    )
}}

select * from {{ ref('stg__tenants') }}

{% endsnapshot %}
