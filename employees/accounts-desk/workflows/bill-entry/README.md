# Bill entry

Reads PDF and image bills for one client business. Each file is read in its own
tool session, every bill in it is routed to the company it is addressed to, and
reviewed bills are saved as verified Purchase, Journal or Debit Note vouchers in
the client's own Tally. A new supplier's ledger is created only when a person
approves it.

- `workflow.json` declares the handler (`desk.bill`), its configuration and the
  sessions it runs (`gpt-6-luna`).
- `SKILL.md` is the procedure: reading the pages, finding the buyer and the
  supplier, and proposing the client's own voucher with `propose`.

The handler owns every check, approval and write; a client's procedure (see
`solutions/<client>/…/bill-entry/`) only adds instructions. See
[Bill entry](../../../../docs/bill-entry.md) for checks, review, writes and
recovery.
