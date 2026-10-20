-- Statement layouts (date order, opening balances) are now learned per bank
-- format and proven by running balances, not tenant settings. Retire only the
-- Statement Entry date_format and opening_balance settings; historical run
-- snapshots, approved manifests and other workflows stay intact.
UPDATE workflows
SET config_values = config_values - ARRAY['date_format', 'opening_balance'],
    config_schema = jsonb_set(
        jsonb_set(config_schema, '{properties}',
            (config_schema->'properties') - ARRAY['date_format', 'opening_balance']),
        '{required}',
        (SELECT coalesce(jsonb_agg(value), '[]'::jsonb)
         FROM jsonb_array_elements(config_schema->'required') AS item(value)
         WHERE value #>> '{}' NOT IN ('date_format', 'opening_balance'))),
    config_version = config_version + 1
WHERE key = 'statement-entry'
  AND (config_values ?| ARRAY['date_format', 'opening_balance']
       OR (config_schema->'properties') ?| ARRAY['date_format', 'opening_balance']);
