# Mock-client Accounts desk

The local mock tenant installs the shared Source discovery and Bill entry
definitions. Initial settings live in `db/fixtures/mock_workflows.json`; operator
defaults are stored in PostgreSQL and are editable in the normal workflow UI.
Client-specific mappings come from confirmed discovery, not source-code fields.

Use the disposable synthetic workspace prepared by
`scripts/prepare_accounts_demo.py`. Its copies contain three Excel workbooks,
three PDF bills and one scanned image. Ground truth, hidden files and the
PR Infra sample directory are excluded from browser inventory. No real-client
connection or file access is provisioned by the seed.

See [the runnable workflow guide](../../../../docs/accounts-desk.md) for setup,
approval, recovery and the web version's local-folder boundary.
