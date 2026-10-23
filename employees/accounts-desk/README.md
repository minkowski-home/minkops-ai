# Accounts desk

Shared employee definition for entering evidenced accounting records in the
client's own Tally.

- `bill-entry`: read bills, route each to the company it is addressed to, and
  propose the client's own voucher for one-click review and a verified save.
- `statement-entry`: read bank statements through a layout proved by their
  balances, route each row to the client's ledgers, and save reviewed, verified
  vouchers.

Both run on the run model: each file or chunk of rows is read in its own tool
session against a pinned copy of the client's books, which the sync keeps
current. Each definition is a versioned contract that a solution installs
explicitly (`mock-client` and `pr-infra` install both). Tenant preferences live
in PostgreSQL; each run pins its configuration and instructions, which grant
no access.
