-- Client profiles: what Minkops learned about one client's practice, derived
-- once and reused. Kinds today: a company's bill posting pattern and a
-- statement file layout; client-memory decision rules (MIN-132) add kinds.
-- At most one live (deriving, proposed or active) version per scope makes
-- derivation single-flight across concurrent batches.
CREATE TABLE client_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('posting_profile', 'statement_layout')),
    scope_key text NOT NULL CHECK (length(scope_key) BETWEEN 1 AND 300),
    version integer NOT NULL CHECK (version > 0),
    schema_version integer NOT NULL DEFAULT 1,
    status text NOT NULL CHECK (status IN ('deriving', 'proposed', 'active', 'superseded', 'invalidated', 'failed')),
    payload jsonb,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    derivation_run_id uuid,
    miss_count integer NOT NULL DEFAULT 0 CHECK (miss_count >= 0),
    invalidated_reason text,
    created_by uuid REFERENCES users(id),
    confirmed_by uuid REFERENCES users(id),
    confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, kind, scope_key, version),
    CHECK (status NOT IN ('proposed', 'active') OR payload IS NOT NULL)
);

CREATE UNIQUE INDEX client_profiles_live ON client_profiles (tenant_id, kind, scope_key)
    WHERE status IN ('deriving', 'proposed', 'active');
