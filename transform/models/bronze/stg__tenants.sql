WITH source AS (
    SELECT *
    FROM {{ source('minkops_app', 'tenants') }}
),

renamed AS (
    SELECT
        id AS tenant_id,
        name AS tenant_name,
        enabled,
        created_at
    FROM source
)

SELECT * FROM renamed