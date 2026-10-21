# Statement entry

Reads CSV/XLSX bank statements through a layout learned once per bank format and
proved against the running balances. Each chunk of rows is routed to the client
business's Tally ledgers in its own tool session, and reviewed rows are saved as
verified Payment, Receipt and Contra vouchers, including lines split across
several ledgers.

- `workflow.json` declares the handler (`desk.statement`), its configuration and
  the sessions it runs (`gpt-6-luna`, with the `layout` stage).
- `SKILL.md` is the procedure for routing rows; `stages/layout.md` declares how a
  new statement format is read.

See [Statement entry](../../../../docs/statement-entry.md) for layouts, routing,
review, writes and recovery.
