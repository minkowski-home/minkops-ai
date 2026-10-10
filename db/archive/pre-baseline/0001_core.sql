-- The OLTP database starts clean. Variable configuration uses validated JSONB;
-- relationships and lifecycle fields remain relational.
CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- a separate tenant_domains table instead of domain field in the tenants table
-- because a tenant might own multiple domains
CREATE TABLE tenant_domains (
    domain text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    verified_at timestamptz,
    CHECK (domain = lower(domain))
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    name text NOT NULL,
    password_hash text NOT NULL,
    email_verified_at timestamptz,
    is_platform_admin boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_unique ON users (lower(email));

CREATE TABLE memberships (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- role has a CHECK constraint and not ENUM ('admin', 'member'), because an ENUM would have its
    -- own lifecycle and migration semantics. Changing its values is more coupled to the database type system.
    -- A text column + CHECK constraint is easy to understand, migrate, query, and serialize through FastAPI.
    role text NOT NULL CHECK (role IN ('admin', 'member')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id)
);
CREATE INDEX memberships_user_id_idx ON memberships (user_id);

CREATE TABLE sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user_id_idx ON sessions (user_id);

CREATE TABLE email_verifications (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL
);

CREATE TABLE invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email text NOT NULL,
    role text NOT NULL CHECK (role IN ('admin', 'member')),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    invited_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invitations_tenant_email_idx ON invitations (tenant_id, lower(email));

CREATE TABLE join_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE employees (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key text NOT NULL,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    config_schema jsonb NOT NULL DEFAULT '{"type":"object","properties":{}}',
    config_values jsonb NOT NULL DEFAULT '{}',
    config_version integer NOT NULL DEFAULT 1 CHECK (config_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, key),
    CHECK (jsonb_typeof(config_schema) = 'object'),
    CHECK (jsonb_typeof(config_values) = 'object')
);
-- employee row cannot exist without a tenant and one particular employee row belongs to exactly one tenant.
-- This table basically represents an employee's customer-specific variant. In the repo, under employees/,
-- we define the employee's product template, but this table only contains a particular client's version
-- of that employee.


CREATE TABLE workflows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key text NOT NULL,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'planned' CHECK (status IN ('active', 'paused', 'planned')),
    config_schema jsonb NOT NULL DEFAULT '{"type":"object","properties":{}}',
    config_values jsonb NOT NULL DEFAULT '{}',
    config_version integer NOT NULL DEFAULT 1 CHECK (config_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, key),
    CHECK (jsonb_typeof(config_schema) = 'object'),
    CHECK (jsonb_typeof(config_values) = 'object')
);
CREATE INDEX workflows_tenant_status_idx ON workflows (tenant_id, status);

CREATE TABLE workflow_employees (
    tenant_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, workflow_id, employee_id),
    FOREIGN KEY (tenant_id, workflow_id) REFERENCES workflows (tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, employee_id) REFERENCES employees (tenant_id, id) ON DELETE CASCADE
);
-- because one workflow can be part of multiple employees and vice versa

CREATE INDEX workflow_employees_employee_idx ON workflow_employees (tenant_id, employee_id);

CREATE TABLE tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    workflow_id uuid,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'attention', 'handoff', 'completed', 'failed')),
    progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    summary text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, workflow_id) REFERENCES workflows (tenant_id, id)
);
CREATE INDEX tasks_tenant_status_idx ON tasks (tenant_id, status, updated_at DESC);


-- task_events is the human/audit timeline for observability - a frontend might use these rows
-- to render task progress, etc.
CREATE TABLE task_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    event_type text NOT NULL,
    summary text NOT NULL,
    progress integer CHECK (progress BETWEEN 0 AND 100),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX task_events_task_idx ON task_events (tenant_id, task_id, id);

-- event_outbox is infrastructure for reliable asynchronous propagation - to make sure
-- some external or downstream process eventually hears about an important database change
CREATE TABLE event_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
CREATE INDEX event_outbox_pending_idx ON event_outbox (created_at) WHERE published_at IS NULL;

-- there must be a separate publisher/relay that scans or consumes unprocessed outbox rows.
-- In our current repo, this is explicitly not built yet. The schema creates the handoff point,
-- but there is no publisher process, broker integration, or Agents API runtime consuming these rows yet.