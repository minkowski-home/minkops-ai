# Statement entry

Read immutable CSV/XLSX snapshots deterministically. Never send bank rows to a hosted model.
Require a manual Branch column and a verified running balance. Resolve normalized branch values uniquely against the pinned company and master discovery. Unknown or ambiguous values remain typed exceptions.
Use an explicit discovered bank ledger per company and the configured Other-side ledger strategy. Write only Payment/Receipt vouchers after preview or standing exception-only authorization. Persist the manifest before native work, read before import, and verify every native voucher. An uncertain import is reconciled without automatically resending it.
