# Mock-client Accounts desk

The local mock tenant installs the shared Source discovery, Statement entry and
Bill entry definitions. Initial settings live in this directory's `binding.json`;
operator defaults are stored in PostgreSQL and are editable in the normal
workflow UI. Client-specific mappings come from confirmed discovery, not
source-code fields. Bill entry adds the client variant in `workflows/bill-entry/`.

The composition's workflow policy enables Tally only. Workflows bind to the
registered Windows PC's open Tally companies; tool selection, company, port and
discovery depth are per-run configurable and restored from the server. No PR
Infra rules or paths are assumed, and the seed provisions no real-client
connection or file access. See
[client-PC source discovery](../../../../docs/source-discovery.md) and the
[five-company rehearsal](../../../../docs/tally-rehearsal.md) for synthetic data.

See [the Accounts desk guide](../../../../docs/accounts-desk.md) for setup,
approval and recovery.
