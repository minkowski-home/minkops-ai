# Bill entry

Reads PDF and image bills, routes each to one company, and proposes the client's
own voucher (Purchase, Journal or Debit Note) from confirmed discovery for
one-click review and a verified save. Client business schemas are discovered and
confirmed; nothing client-specific is encoded here.

- `workflow.json` declares the handler (`accounts.bill`), tenant and run
  configuration, the hosted execution bundle (`gpt-6-luna`) and its stages.
- `SKILL.md` and `execution-instructions.md` guide the main extraction turn;
  `stages/triage.md` routes bills to companies first and
  `stages/posting-profile.md` derives a company's posting pattern once.
- `agent-output.schema.json` and each stage's schema validate hosted proposals
  before review. `output.schema.json` is the descriptor's generic result
  contract; Accounts does not validate against it.

The application owns approvals, business checks and verified writes; client
instructions (see `solutions/<client>/…/bill-entry/`) are additive. See
[Bill entry](../../../../docs/bill-entry.md) for settings, review decisions,
recovery and verification.
