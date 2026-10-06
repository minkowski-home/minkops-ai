# Bill entry (MIN-119): mock-client demonstration

MIN-119 connects the shared desktop/web review to MIN-117's registered Windows
companion and MIN-118's confirmed source catalogs. The demo seed activates the
workflow only for `mock-tenant`. No PR Infra rules or customer data are added.
The existing hosted Agents API runs all Accounts proposals on `gpt-6-luna`;
launch rejects another model. The model never writes financial systems.

## Workflow

1. Connect the Windows PC and grant the destination folder. Run Source discovery
   and confirm the Excel destination mappings, or discover the selected Tally
   company, ledgers and Purchase voucher type and confirm that catalog.
2. Upload/select PDFs and images. Select Excel or Tally output in Bill entry.
   Multiple inputs create independent durable hosted sessions under one task.
   Four worker lanes process them concurrently; a provider failure affects only
   its bill. The parent aggregates persisted proposals and unresolved inputs.
3. Review source evidence and values. Approve, hold, reject or edit each entry.
   Good entries can be saved while other bills need clarification. Supply input
   for an unresolved bill to retry only that input; completed sibling writes stay
   intact. Tally requires review of every output. Excel retains its existing
   optional exceptions-only policy and deterministic checks.
4. Approval commits immutable plans and queues native work before returning.
   The tray companion can finish after the UI closes. Web and desktop use the
   same API, review component and task state. A browser-only Excel folder still
   needs an open page and its local permission.

## Source accuracy and recovery

Business identity uses supplier, invoice number and Indian April–March financial
year when those confirmed concepts exist. Excel otherwise uses complete confirmed
business keys. IDs do not depend on a task, uploaded filename or processing order.
Existing external rows/vouchers and backfills are checked against destination
data, rather than relying only on prior application history.

Exact duplicates produce an alert and no additional row/voucher. A different
version is held for explicit Edit. Excel corrections compare observed values
against extraction-time values and recheck current destination bytes. Tally
corrections compare the complete fetched voucher fingerprint, then target its
observed original date and MASTER ID. Another intervening edit requires another
review. Updates retain the observed voucher GUID; Tally may assign its own GUID
on creation.

Pending writes reserve the workbook, or the company GUID and bill identity,
across runs and registered PCs. Confirmed Tally company/ledger identities and
versions are rechecked natively before saving. Each write requires exact saved
bytes or voucher/ledger/amount readback. Completion of one native job cannot
complete a batch with pending or held bills.

Consequential jobs are not automatically repeated after lease expiry. Explicit
Resume saves first reconciles the destination, handling an already applied write
without adding it again. Persisted receipts are replayed before another native
job. Cancellation releases pending reservations and preserves applied changes.
A late cancelled receipt records what was saved without restoring success or
rewinding newer observed workbook bytes. Independent external writers can still
race Tally's separate read/import calls: ambiguous matches or mismatched readback
require reconciliation, never a claimed successful save.

## Supported mapping

Excel uses actual confirmed headers, sheet/table boundaries and types; it does
not impose a universal invoice schema. Existing workbook protections, formulas,
styles, hash checks, native backups and atomic replacement remain in force.

The Tally mock contract is a balanced accounting Purchase voucher:
`invoice_number`, `vendor`, `date`, `purchase_ledger`, `subtotal`, `tax`,
`tax_ledger`, `total`, and nullable `cost_code`. Supplier, purchase and nonzero tax
allocations must use distinct discovered ledgers. Money must reconcile exactly
at two decimal places and fit exact native cents. The demo's combined tax ledger
is synthetic, not a statutory GST filing configuration.

Inventory invoices, bill/payment/cost allocations and additional ledger splits
need a richer connector contract; corrections containing those allocations are
held so they cannot be flattened. Unsupported cost allocations also require
review. Client-specific rules belong in versioned employee workflow definitions,
tenant preferences and solution composition, alongside deterministic platform
validation and connector capabilities. No real-client rules are guessed.

The adapter uses bounded fixed XML exports/imports on the PC's loopback port;
there is no renderer-supplied XML, URL, TDL or shell. Tally's documented correction
selector needs its original DATE and MASTER ID. References:
[Tally sample XML](https://help.tallysolutions.com/sample-xml/) and
[Tally voucher alteration](https://help.tallysolutions.com/scenario-2/).

## Complex synthetic fixtures

Generate a fresh set with the existing Python stack plus development-only PDF
libraries:

```sh
uv run --all-packages --with reportlab --with pymupdf python scripts/prepare_bill_entry_demo.py
```

The script refuses to overwrite an existing demo folder. `--refresh-scans`
rerenders only generated PDFs, preserving an already tested workbook.
Files appear in `apps/solution-api/data/min119-hard-demo`; ground truth is outside
the synchronized input folder. Each readable bill includes two pages, dense
small text, skew, stamps, competing PO/GRN/date identifiers, trading and registered
names, gross/discount/base amounts, split tax, excluded prior balances, repeated
totals and an allocation memo. Scan PDFs contain raster pages with no text layer.
The set includes new bills, a backfill, a correction and a valid blank image.
The register uses obscure headers such as `Party.External`, `Txn.Base` and
`Settlement.Due`, requiring discovery and extraction to infer business meaning.

Only the explicitly selected test company should be used. Seed mock supplier,
purchase and tax ledgers there before the live proof; do not overwrite existing
masters. Apply migrations through 0010 and seed the isolated demo database.

## Verification

Offline tests replace the paid proposal boundary and exercise real PostgreSQL,
authenticated API transport and immutable financial plans. They cover
117/118/119 wiring, parallel sessions, isolated failures, duplicate uploads,
backfills, corrections, stale review, cross-PC reservations, receipt replay,
lease expiry, cancellation and late receipts. Native tests run on Windows and
Linux and include the Tally alteration selector regression. Shared UI build,
lint and existing web tests are run; visual and Windows installation QA remain
MIN-122.

Opt-in live proofs use the dedicated `minkops_min119_live` database. From WSL,
set `DATABASE_URL`, `MINKOPS_TALLY_TEST_COMPANY` and `MINKOPS_WINDOWS_NODE` to the
Windows Node executable. `MINKOPS_WINDOWS_ROOT` is optional; otherwise `wslpath`
resolves this checkout. Model credentials are loaded only in the server process
and removed from the Windows adapter environment.

```sh
uv run --all-packages python scripts/verify_bill_entry_live.py
uv run --all-packages python scripts/verify_bill_entry_excel_live.py
```

The Tally script prints the batch ID and supports `--resume ID` after an
interruption. The Excel proof saves checkpoint IDs beside the generated fixtures.
Both reconcile persisted sessions; they do not resend completed input. The live
proofs verified all three readable hard scans against independent expected
values, Tally writes/readback, schema discovery, extraction into exact complex
Excel headers, a native workbook save and repeated receipts. A provider rate
limit interrupted the blank-image turn; explicit retry isolated that image and
retained three verified sibling saves.
