# Native desktop connectors

The Windows companion's native adapters. `index.js` exports only what the
companion and its operator scripts call; tests import the modules directly.

- `index.js`: the companion's native surface, and bounded snapshots of a
  granted folder.
- `sync.js`: the read-only sync of a company's masters and vouchers into the
  server's mirror, in markers, deltas, censuses and bounded pages.
- `tally-references.js`: fixed, bounded master reads that check a write's
  destination and read back a created supplier.
- `tally-session.js`: the user's own Tally session (open companies, typed
  states, bounded HTTP/XML transport). It never starts, closes or configures Tally.
- `voucher.js`: the plan protocol 5 writer for every voucher family, with
  durable intent before import and independent readback.
- `tally.js`: GST supplier creation a person approved, verified by readback.

No task dispatch, API transport or AI execution loop lives here; those belong to
`platform/desktop-runtime` and the server. Node 24 development: `npm ci && npm test`.
