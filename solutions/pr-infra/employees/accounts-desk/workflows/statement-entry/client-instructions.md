- **Site codes.** The statement's remarks carry PR Infra's site codes. They are a
  routing label, never a ledger name: use them as the routing hint, through the
  client's mapping when one is offered.
- **Related company.** Large receipts often come from a related company. Look for
  its intercompany ledger by that company's name before treating a receipt as
  income.
- **Bulk NEFT batches.** One statement line can pay many individual payees. How
  PR Infra books these batches is not yet settled: hold such a row with
  `ledger_unresolved` and say it is a batch.
