# Statement entry

Reads CSV/XLSX bank statements through a layout learned once per bank format and
proved against running balances, routes each line to confirmed ledgers using
pinned discovery, and saves reviewed, verified Payment, Receipt and Contra
vouchers (including lines split across several ledgers).

- `workflow.json` declares the handler (`accounts.statement`), configuration,
  the hosted execution bundle (`gpt-6-luna`) and the `layout` stage.
- `SKILL.md` and `execution-instructions.md` guide classification;
  `stages/layout.md` declares how a new statement format is read.
- `agent-output.schema.json` and `stages/layout.schema.json` validate hosted
  proposals. `output.schema.json` is the descriptor's generic result contract;
  Accounts does not validate against it.

See [Statement entry](../../../../docs/statement-entry.md) for layouts,
routing, preview, writes and recovery.
