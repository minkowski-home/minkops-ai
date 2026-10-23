-- Public polling must not repeatedly decode a full native Tally catalog.
-- The application derives the display once per catalog version. Company names
-- have their own small projection for comparing discovery scopes.
ALTER TABLE discovery_runs ADD COLUMN public_catalog jsonb;
ALTER TABLE discovery_runs ADD COLUMN catalog_version bigint NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN company_scope jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE FUNCTION discovery_catalog_changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.public_catalog := NULL;
    IF TG_OP='UPDATE' THEN NEW.catalog_version := OLD.catalog_version+1;
    ELSE NEW.catalog_version := 1; END IF;
    SELECT coalesce(jsonb_object_agg(c->>'company_guid',c->>'company'),'{}'::jsonb)
        INTO NEW.company_scope
        FROM jsonb_array_elements(coalesce(NEW.catalog->'sources','[]'::jsonb)) s,
             jsonb_array_elements(coalesce(s#>'{snapshot,companies}','[]'::jsonb)) c
        WHERE s->>'tool'='tally' AND c->>'company_guid' IS NOT NULL;
    RETURN NEW;
END $$;
CREATE TRIGGER discovery_catalog_projection BEFORE INSERT OR UPDATE OF catalog ON discovery_runs
    FOR EACH ROW EXECUTE FUNCTION discovery_catalog_changed();
UPDATE discovery_runs SET catalog=catalog;
