# Native desktop connectors

The Windows companion's native adapters. `index.js` exports only what the
companion and its operator scripts call; tests import the modules directly.

- `index.js`: bounded folder snapshots and approved workbook replacement with
  hash, backup and readback checks.
- `discovery.js`, `client-context.js`, `tally-references.js`: workbook
  projections and Tally master/voucher exports for Source discovery.
- `tally-session.js`: the user's own Tally session (open companies, typed
  states, bounded HTTP/XML transport). It never starts, closes or configures Tally.
- `voucher.js`: the plan protocol 5 writer for every voucher family, with
  durable intent before import and independent readback.
- `tally.js`: earlier bill plans (protocols 1–3) that the server cannot upgrade,
  Attention rechecks and verified GST supplier creation.

No task dispatch, API transport or AI execution loop lives here; those belong to
`platform/desktop-runtime` and the server. Node 24 development: `npm ci && npm test`.
