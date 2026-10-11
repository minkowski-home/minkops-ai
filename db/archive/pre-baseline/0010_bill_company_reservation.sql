-- A company observed on two registered PCs is still one financial destination.
-- Prefer its observed GUID; legacy catalogs without one remain device-scoped.
ALTER TABLE account_tally_writes ADD COLUMN destination_key text;
UPDATE account_tally_writes SET destination_key=coalesce(
 'company:' || nullif(plan->'references'->>'company_guid',''),
 'device:' || device_id::text || ':' || company);
ALTER TABLE account_tally_writes ALTER COLUMN destination_key SET NOT NULL;
DROP INDEX account_tally_pending;
CREATE UNIQUE INDEX account_tally_pending ON account_tally_writes(tenant_id,destination_key,identity)
 WHERE finished_at IS NULL AND cancelled_at IS NULL;
