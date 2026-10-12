-- Remove the retired preference from installed workflows without rewriting
-- immutable discovery catalogs or the execution contracts of already pinned runs.
UPDATE workflows
SET config_values = config_values - 'discovery_depth',
    config_schema = jsonb_set(
        jsonb_set(config_schema, '{properties}',
            coalesce(config_schema->'properties', '{}'::jsonb) - 'discovery_depth'),
        '{required}', coalesce(config_schema->'required', '[]'::jsonb) - 'discovery_depth'
    ),
    config_version = config_version + 1
WHERE (key = 'source-discovery' OR execution_binding->>'presentation' = 'accounts-discovery')
  AND (config_values ? 'discovery_depth'
       OR config_schema->'properties' ? 'discovery_depth'
       OR config_schema->'required' ? 'discovery_depth');
