-- Rebuild tenancy: tenant -> client business -> company, with per-client
-- access for accounting practices.

-- A single business lets every member reach every client business; an
-- accounting practice scopes members to the clients granted to them.
ALTER TABLE tenants ADD COLUMN client_scoping boolean NOT NULL DEFAULT false;

CREATE TABLE client_businesses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    slug text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, slug)
);

CREATE TABLE client_access (
    tenant_id uuid NOT NULL,
    client_id uuid NOT NULL,
    user_id uuid NOT NULL,
    granted_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, client_id, user_id),
    FOREIGN KEY (tenant_id, client_id) REFERENCES client_businesses(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, user_id) REFERENCES memberships(tenant_id, user_id) ON DELETE CASCADE
);

-- A Tally company as one PC sees it. GUIDs alone are not identities: split
-- companies can share one, so PC, GUID and BooksFrom form the key and name and
-- number are checked. A new company is never mirrored until it is authorised.
CREATE TABLE companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    client_id uuid,
    device_id uuid NOT NULL,
    guid text NOT NULL CHECK (length(guid) BETWEEN 1 AND 200),
    books_from date NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    company_number text CHECK (company_number ~ '^[0-9]{1,10}$'),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'authorised', 'declined')),
    decided_by uuid REFERENCES users(id),
    decided_at timestamptz,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, device_id, guid, books_from),
    CHECK (status <> 'authorised' OR client_id IS NOT NULL),
    FOREIGN KEY (tenant_id, client_id) REFERENCES client_businesses(tenant_id, id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id)
);
CREATE INDEX companies_client ON companies (tenant_id, client_id) WHERE status = 'authorised';

-- Tasks of client work carry their client, so lists filter by access.
ALTER TABLE tasks ADD COLUMN client_id uuid;
ALTER TABLE tasks ADD CONSTRAINT tasks_client FOREIGN KEY (tenant_id, client_id)
    REFERENCES client_businesses(tenant_id, id);
CREATE INDEX tasks_client_idx ON tasks (tenant_id, client_id, updated_at DESC) WHERE client_id IS NOT NULL;
