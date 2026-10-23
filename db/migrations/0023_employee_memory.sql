-- Employee memory: runtime data per client business and employee, shared by
-- all of that employee's workflows and looked up only when a session needs it.
-- The structured part is learnt from one-click answers and from outcomes that
-- were verified and accepted; the plain-text part is only ever written by people.

CREATE TABLE memory_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    client_id uuid NOT NULL,
    employee_key text NOT NULL CHECK (employee_key ~ '^[a-z][a-z0-9-]{0,40}$'),
    -- NULL applies to every company of the client business.
    company_id uuid,
    kind text NOT NULL CHECK (kind ~ '^[a-z][a-z_]{0,40}$'),
    subject text NOT NULL CHECK (length(subject) <= 300),
    value jsonb NOT NULL,
    -- The native identities the value refers to, revalidated on every sync.
    guids text[] NOT NULL DEFAULT '{}',
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence) = 'array'),
    status text NOT NULL CHECK (status IN ('unconfirmed', 'confirmed', 'demoted', 'retired', 'disabled')),
    misses integer NOT NULL DEFAULT 0 CHECK (misses >= 0),
    uses integer NOT NULL DEFAULT 0 CHECK (uses >= 0),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    confirmed_by uuid REFERENCES users(id),
    confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, client_id) REFERENCES client_businesses(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE
);
-- One live entry per subject; retired entries stay as history.
CREATE UNIQUE INDEX memory_entries_live ON memory_entries
    (tenant_id, client_id, employee_key, coalesce(company_id::text, ''), kind, subject) WHERE status <> 'retired';

CREATE TABLE memory_instructions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    client_id uuid NOT NULL,
    employee_key text NOT NULL CHECK (employee_key ~ '^[a-z][a-z0-9-]{0,40}$'),
    -- Scope: NULL means every workflow of the employee, or every company.
    workflow_key text CHECK (workflow_key ~ '^[a-z][a-z0-9-]*$'),
    company_id uuid,
    text text NOT NULL CHECK (length(btrim(text)) BETWEEN 1 AND 2000),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_by uuid REFERENCES users(id),
    updated_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, client_id) REFERENCES client_businesses(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE
);

-- Proposals cite an instruction by ID and version, so every version is kept.
CREATE TABLE memory_instruction_versions (
    tenant_id uuid NOT NULL,
    instruction_id uuid NOT NULL,
    version integer NOT NULL,
    text text NOT NULL,
    workflow_key text,
    company_id uuid,
    status text NOT NULL,
    actor_id uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (instruction_id, version),
    FOREIGN KEY (tenant_id, instruction_id) REFERENCES memory_instructions(tenant_id, id) ON DELETE CASCADE
);

-- Every memory action records its actor (none for the sync's own probes).
CREATE TABLE memory_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id uuid NOT NULL,
    entry_id uuid,
    instruction_id uuid,
    actor_id uuid REFERENCES users(id),
    action text NOT NULL CHECK (action ~ '^[a-z][a-z_]{0,30}$'),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX memory_events_entry ON memory_events (entry_id, id) WHERE entry_id IS NOT NULL;

-- A practice probe the mirror could not settle becomes one one-click question
-- per company. Bills that depend on it hold; the answer releases them.
CREATE TABLE practice_questions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    client_id uuid NOT NULL,
    company_id uuid NOT NULL,
    employee_key text NOT NULL,
    probe text NOT NULL CHECK (probe ~ '^[a-z][a-z_]{0,40}$'),
    prompt text NOT NULL CHECK (length(prompt) BETWEEN 1 AND 500),
    options jsonb NOT NULL CHECK (jsonb_typeof(options) = 'array'),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'dismissed')),
    answer jsonb,
    answered_by uuid REFERENCES users(id),
    answered_at timestamptz,
    attention_item_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, client_id) REFERENCES client_businesses(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX practice_questions_open ON practice_questions (tenant_id, company_id, probe) WHERE status = 'open';
