WITH source AS (
    SELECT *
    FROM {{ source('minkops_app', 'synthetic_orders') }}
),

renamed AS (
    SELECT
        order_id,
        tenant_id,
        customer_id,
        source_session_id,
        order_number,
        order_status,
        payment_method,
        currency_code,
        ordered_at,
        paid_at,
        fulfilled_at,
        canceled_at,
        subtotal_usd,
        discount_usd,
        shipping_usd,
        tax_usd,
        refund_usd,
        total_usd,
        margin_usd,
        line_item_count,
        sla_target_hours,
        created_at AS record_created_at
    FROM source
)

SELECT * FROM renamed