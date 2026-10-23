-- The short references an item's lookups issued, such as C1 for a company or
-- L12 for a ledger. Sessions read and propose companies and masters only by
-- them: Tally numbers a company's masters in sequence, so a GUID a session
-- guessed or mistyped could name another real master, while a reference no
-- lookup issued names none. Each stands for one company or master, the same
-- one for the whole item, so a resumed session keeps the references it read.
CREATE TABLE item_refs (
    tenant_id uuid NOT NULL,
    item_id uuid NOT NULL,
    ref text NOT NULL CHECK (ref ~ '^[A-Z][1-9][0-9]{0,4}$'),
    kind text NOT NULL CHECK (kind IN ('company', 'ledger', 'stock_item', 'godown', 'voucher_type', 'cost_centre')),
    -- The company the master belongs to; a company's own reference names itself.
    company_guid text NOT NULL,
    guid text NOT NULL,
    PRIMARY KEY (item_id, ref),
    UNIQUE (item_id, kind, company_guid, guid),
    FOREIGN KEY (tenant_id, item_id) REFERENCES run_items(tenant_id, id) ON DELETE CASCADE
);
