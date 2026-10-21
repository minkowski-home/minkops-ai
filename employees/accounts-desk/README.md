# Accounts desk

Shared employee definition for entering evidenced accounting records in the
client's own Tally.

- `source-discovery`: collect the client's Tally masters, period vouchers and
  workbook structure, and propose reviewed context for the other workflows.
- `bill-entry`: read bills, route each to one company and propose the client's
  own voucher for one-click review and a verified save.
- `statement-entry`: read bank statements through a learned layout, route each
  line to confirmed ledgers and save reviewed, verified vouchers.

Each definition is a versioned contract that a solution installs explicitly
(`mock-client` installs all three; `pr-infra` installs Source discovery and
Statement entry). Tenant preferences live in PostgreSQL. Each run stores its
resolved configuration and definition/catalog versions; instructions do not
grant access.
