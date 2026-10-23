-- The server-side Tally mirror: one versioned copy per PC and company, kept by
-- a no-AI sync. Rows carry synced_in/superseded_in; a run pins one version and
-- sees exactly the rows visible at it, so a sync can publish mid-run.

CREATE TABLE mirror_versions (
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    kind text NOT NULL CHECK (kind IN ('full', 'delta')),
    state text NOT NULL DEFAULT 'building' CHECK (state IN ('building', 'published', 'abandoned')),
    job_id uuid,
    reason text NOT NULL CHECK (length(reason) <= 80),
    -- Company markers read before collection began; committed only at publish.
    markers jsonb NOT NULL CHECK (jsonb_typeof(markers) = 'object'),
    -- {from, to}: the voucher window this version covers.
    coverage jsonb NOT NULL CHECK (jsonb_typeof(coverage) = 'object'),
    -- Independent per-date voucher counts from Tally, the census guard's evidence.
    counts jsonb,
    swept boolean NOT NULL DEFAULT false,
    stats jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    PRIMARY KEY (company_id, version),
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, job_id) REFERENCES desktop_jobs(tenant_id, id)
);
-- One sync builds a company's next version at a time.
CREATE UNIQUE INDEX mirror_versions_building ON mirror_versions (company_id) WHERE state = 'building';
CREATE INDEX mirror_versions_published ON mirror_versions (company_id, version DESC) WHERE state = 'published';

CREATE TABLE mirror_masters (
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    guid text NOT NULL,
    synced_in integer NOT NULL,
    superseded_in integer,
    -- The latest version that fetched this exact row again; a full rebuild
    -- tombstones current rows it did not see.
    seen_in integer NOT NULL,
    type text NOT NULL CHECK (type ~ '^[A-Z][A-Z0-9]{0,40}$'),
    name text NOT NULL,
    name_key text NOT NULL,
    parent text,
    alter_id bigint,
    digest text NOT NULL,
    aliases text[] NOT NULL DEFAULT '{}',
    gstin text,
    bank_account text,
    ifsc text,
    hsn text,
    data jsonb NOT NULL,
    PRIMARY KEY (company_id, guid, synced_in),
    CHECK (superseded_in IS NULL OR superseded_in > synced_in),
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX mirror_masters_current ON mirror_masters (company_id, guid) WHERE superseded_in IS NULL;
CREATE INDEX mirror_masters_lookup ON mirror_masters (company_id, type, name_key);
CREATE INDEX mirror_masters_gstin ON mirror_masters (gstin, company_id) WHERE gstin IS NOT NULL;
CREATE INDEX mirror_masters_bank ON mirror_masters (company_id, bank_account) WHERE bank_account IS NOT NULL;

CREATE TABLE mirror_vouchers (
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    guid text NOT NULL,
    synced_in integer NOT NULL,
    superseded_in integer,
    seen_in integer NOT NULL,
    master_id bigint,
    alter_id bigint NOT NULL,
    date date NOT NULL,
    voucher_type text NOT NULL,
    number text NOT NULL DEFAULT '',
    reference text NOT NULL DEFAULT '',
    party_ledger text NOT NULL DEFAULT '',
    party_key text NOT NULL DEFAULT '',
    narration text NOT NULL DEFAULT '',
    cancelled boolean NOT NULL DEFAULT false,
    optional boolean NOT NULL DEFAULT false,
    postdated boolean NOT NULL DEFAULT false,
    ledgers text[] NOT NULL DEFAULT '{}',
    digest text NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (company_id, guid, synced_in),
    CHECK (superseded_in IS NULL OR superseded_in > synced_in),
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX mirror_vouchers_current ON mirror_vouchers (company_id, guid) WHERE superseded_in IS NULL;
CREATE INDEX mirror_vouchers_date ON mirror_vouchers (company_id, date);
CREATE INDEX mirror_vouchers_party ON mirror_vouchers (company_id, party_key, date DESC);
CREATE INDEX mirror_vouchers_ledgers ON mirror_vouchers USING gin (ledgers);

-- New Ref and Agst Ref allocations, derived from vouchers for open_bills.
CREATE TABLE mirror_bill_refs (
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    voucher_guid text NOT NULL,
    synced_in integer NOT NULL,
    superseded_in integer,
    ledger text NOT NULL,
    ledger_key text NOT NULL,
    name text NOT NULL,
    bill_type text NOT NULL,
    amount_cents bigint NOT NULL,
    date date NOT NULL,
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX mirror_bill_refs_open ON mirror_bill_refs (company_id, ledger_key, name);
CREATE INDEX mirror_bill_refs_voucher ON mirror_bill_refs (company_id, voucher_guid) WHERE superseded_in IS NULL;

-- Sync pages are accepted once by sequence; a resent page must be identical.
CREATE TABLE sync_pages (
    job_id uuid NOT NULL,
    seq integer NOT NULL CHECK (seq >= 0),
    digest text NOT NULL,
    response jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, seq)
);

ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK (operation = ANY (ARRAY[
    'tally.probe', 'files.refresh', 'accounts.save', 'tally.save', 'sources.discover', 'tally.references',
    'attention.refresh', 'attention.supplier', 'tally.statement', 'tally.sync']));

-- The port this PC's Tally serves on; every sync and save plan carries it.
ALTER TABLE desktop_devices ADD COLUMN tally_port integer NOT NULL DEFAULT 9000 CHECK (tally_port BETWEEN 1 AND 65535);
