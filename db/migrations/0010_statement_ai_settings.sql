-- Retire only Statement Entry's classification defaults. Historical run
-- snapshots, approved manifests, receipts and all other workflows stay intact.
UPDATE workflows
SET config_values = config_values - ARRAY['other_side_ledger', 'counter_mode'],
    config_schema = jsonb_set(
        jsonb_set(config_schema, '{properties}',
            (config_schema->'properties') - ARRAY['other_side_ledger', 'counter_mode']),
        '{required}',
        (SELECT coalesce(jsonb_agg(value), '[]'::jsonb)
         FROM jsonb_array_elements(config_schema->'required') AS item(value)
         WHERE value #>> '{}' NOT IN ('other_side_ledger', 'counter_mode'))),
    config_version = config_version + 1
WHERE key = 'statement-entry'
  AND (config_values ?| ARRAY['other_side_ledger', 'counter_mode']
       OR (config_schema->'properties') ?| ARRAY['other_side_ledger', 'counter_mode']);
