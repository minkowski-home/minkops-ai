-- Each bank ledger's opening and closing balance in one run's statements, as
-- its rows chained. A later statement that opens at a different balance than
-- the previous one closed raises one "Transactions missing" item.
CREATE TABLE statement_spans (
    tenant_id uuid NOT NULL,
    run_id uuid NOT NULL,
    company_id uuid NOT NULL,
    bank_ledger text NOT NULL,
    date_from date NOT NULL,
    date_to date NOT NULL,
    opening_cents bigint NOT NULL,
    closing_cents bigint NOT NULL,
    PRIMARY KEY (run_id, company_id, bank_ledger),
    FOREIGN KEY (tenant_id, run_id) REFERENCES runs(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, company_id) REFERENCES companies(tenant_id, id)
);
CREATE INDEX statement_spans_ledger ON statement_spans (company_id, bank_ledger, date_to DESC);
