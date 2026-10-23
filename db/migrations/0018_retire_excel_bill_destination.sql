-- Bill Entry writes only to Tally from 0.18: retire its output-mode setting so
-- installation can validate stored settings against the new schema. Historical
-- run snapshots, approved plans, receipts and other workflows stay intact.
UPDATE workflows
SET config_values = config_values - 'output_mode',
    config_schema = jsonb_set(
        jsonb_set(config_schema, '{properties}', (config_schema->'properties') - 'output_mode'),
        '{required}',
        (SELECT coalesce(jsonb_agg(value), '[]'::jsonb)
         FROM jsonb_array_elements(config_schema->'required') AS item(value)
         WHERE value #>> '{}' <> 'output_mode')),
    config_version = config_version + 1
WHERE key = 'bill-entry'
  AND (config_values ? 'output_mode' OR (config_schema->'properties') ? 'output_mode');
