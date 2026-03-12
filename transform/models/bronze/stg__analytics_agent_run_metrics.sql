WITH source AS (
    SELECT *
    FROM {{ source('minkops_app', 'analytics_agent_run_metrics') }}
),

renamed AS (
    SELECT
        run_metric_id,
        tenant_id,
        run_date,
        run_started_at,
        run_finished_at,
        agent_id,
        trigger_type,
        outcome_status,
        latency_ms,
        prompt_tokens,
        completion_tokens,
        tool_calls,
        retry_count,
        human_escalation,
        model_cost_usd,
        revenue_impact_usd,
        source_run_id,
        created_at AS run_metric_row_created_at
    FROM source
)

SELECT * FROM renamed