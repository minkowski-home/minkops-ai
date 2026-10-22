-- A company continued on the PC that replaces its disconnected one. The PC
-- finds the same books (GUID and BooksFrom) as a newly found company; an
-- admin's decision moves the client's existing company to that PC, keeping
-- everything keyed to it (memory, rules, practice, statement continuity, saves
-- and mirror versions), and removes the newly found duplicate. Each move is
-- kept: who moved the books from which PC to which, and when. A decision sent
-- again for the removed duplicate finds the company it continued here.
CREATE TABLE company_moves (
    tenant_id uuid NOT NULL,
    found_id uuid NOT NULL,
    company_id uuid NOT NULL,
    from_device_id uuid NOT NULL,
    to_device_id uuid NOT NULL,
    moved_by uuid REFERENCES users(id),
    moved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, found_id),
    CHECK (from_device_id <> to_device_id),
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, from_device_id) REFERENCES desktop_devices(tenant_id, id),
    FOREIGN KEY (tenant_id, to_device_id) REFERENCES desktop_devices(tenant_id, id)
);
CREATE INDEX company_moves_company ON company_moves (company_id, moved_at DESC);
