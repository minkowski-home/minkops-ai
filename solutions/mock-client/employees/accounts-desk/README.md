# Mock-client Accounts desk

The local mock tenant installs the shared Statement entry and Bill entry
definitions. Initial settings live in this directory's `binding.json`; operator
defaults are stored in PostgreSQL and are editable in the normal workflow UI.
Bill entry adds the client variant in `workflows/bill-entry/`.

Runs read the client's companies through the sync of the registered Windows PC's Tally; no PR Infra
rules or paths are assumed, and the seed provisions no real-client connection or
file access. See the [five-company rehearsal](../../../../docs/tally-rehearsal.md)
for synthetic data, and [the Accounts desk guide](../../../../docs/accounts-desk.md)
for setup, approval and recovery.
