# Bill entry (MIN-119): mock-client demonstration

MIN-119 connects the shared desktop/web review to MIN-117's registered Windows
companion and MIN-118's confirmed source catalogs. The demo seed activates the
workflow only for `mock-tenant`. No PR Infra rules or customer data are added.
The existing hosted Agents API runs all Accounts proposals on `gpt-6-luna`;
launch rejects another model. The model never writes financial systems.

## Workflow

1. Connect the Windows PC and grant the destination folder. Run Source discovery
   and confirm Excel header mappings, then explicitly refresh the real workbook
   before using it as a destination. For Tally, confirm the selected company's
   complete version 2 context package. Each run pins company identities, full
   masters, recent vouchers and reviewed notes as authorized JSON inputs; Bill
   Entry has no schema search or reference collection job.
2. Choose one locked company for the run, or let each bill route to any company
   in discovery using buyer identity and evidenced client context. The scan saves
   its company GUID and selection evidence; uncertain routing requires handoff.
   Upload/select PDFs and images. Excel, Tally and Both remain visible configuration
   choices. Mock-client's trusted solution policy enables only Tally for Bill entry;
   disabled choices cannot be enabled by changing preferences or launch payloads.
   Source discovery independently supports Excel, Tally and Both.
   Combined Bill entry writes are reserved for a later verified adapter contract;
   the API rejects Both rather than silently using only one destination.
   Multiple inputs create independent durable hosted sessions under one task.
   Four worker lanes process them concurrently; a provider failure affects only
   its bill. The parent aggregates persisted proposals and unresolved inputs.
3. Review concise bill identifiers and choose Write bill, Best guess write,
   Create this ledger (when supported), or Do nothing. Accounting corrections
   belong in Tally/Excel; Minkops has no value editor, correction prompt or
   append/update selector. After external correction and discovery refresh,
   Recheck bill retries only that unresolved input. Completed sibling writes stay
   intact. Good bills can continue independently. See [shared attention](attention.md).
4. All scans are persisted before approval. Approval commits immutable plans
   and queues serial native work grouped by company before returning.
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
version is held for an explicit one-click decision. Excel corrections compare observed values
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

The current RC fixtures, generated history, source catalogs and evidence live in
`C:\Users\gauss\OneDrive\Minkops\MockClient\ReleaseCandidate-20261006`, outside
the repository and iCloud. Four vendors provide a cement tax invoice, skewed steel
phone photo, faint aggregate carbon copy and two-page equipment hire bill. A JPEG
copy of the steel PDF exercises duplicate identities across files. Separate
`evidence/expected-bills.json` records exact dates, ledgers and amounts.

Test Company is preserved: baseline exports capture every original voucher and
master before adding RC-prefixed suppliers, purchase/tax ledgers, units, stock
items and site references, plus two history vouchers. The hire supplier is
initially absent. Its bill appears in Needs Attention while known bills save;
after creating the supplier and confirming discovery, only that bill is retried.
No live Excel data or writes are included in this RC.
The three display-only seed tasks are backed up and removed from the RC database
so its Active/Needs Attention sections reflect executable workflow outcomes.

Discovery is mandatory before dependent workflows, with manual refresh afterward.
Its date range applies only to vouchers; all masters are exported comprehensively.
New runs use Source Discovery 0.7.2, Bill Entry 0.9.0 and companion 0.6.0. The RC
evidence below predates this refactor. Repeat live acceptance and deployment under
[MIN-124](https://linear.app/minkops/issue/MIN-124). No scheduling or new accounting
layer is introduced. The existing native Purchase contract remains bounded.

Tally HTTP/XML errors produce local diagnostics with available Windows crash events.
If a known Tally process disappears, the companion may restart it once using its
observed executable and safe numeric `/LOAD` arguments, then wait for companies.
Reads may repeat once; an uncertain import is never automatically resent. Read-only
reconciliation distinguishes an already-applied bill, a conflicting version and
an absent bill requiring review/Resume. If restart, login or readback cannot be
established, the run remains unresolved. See [Windows recovery](windows-app.md).

The following generator and live scripts describe the earlier development proof.
Do not run them against this preserved Test Company: their fixed fixture IDs
belong to that earlier disposable environment.

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
masters. Run `db/migrate.py` against the isolated demo database to install or adopt
the final baseline, then seed its demo composition.

## Verification

Offline tests replace the paid proposal boundary and exercise real PostgreSQL,
authenticated API transport and immutable financial plans. They cover
117/118/119 wiring, parallel sessions, isolated failures, duplicate uploads,
backfills, corrections, stale review, cross-PC reservations, receipt replay,
lease expiry, cancellation and late receipts. Native tests run on Windows and
Linux and include the Tally alteration selector regression. Shared UI build,
lint and existing web tests are run. The 6 October RC additionally verifies the
installed Windows 0.3.1 app, folder picker, catalog Save As, four desktop themes,
shared web review at the minimum desktop width, source previews, and tray/reopen
execution. See `docs/windows-app.md` for distribution limitations.
That historical RC showed expandable evidence and findings. The current review
shows concise identifiers and one-click decisions; detailed evidence and logs
remain internal. See [attention](attention.md) and [current verification](verification-min-124.md).

The 6 October proof used `minkops_mock_rc20261006`, with an independently migrated
`minkops_min119_tests` database for regression tests. Initial extraction saves
four unique bills and skips the steel copy. A complete second run skips all five
inputs after an ambiguous steel reference is clarified independently; it creates
no additional vouchers. Worker restart retains existing paid session IDs. Live
correction verification holds a changed RC history voucher before import, then
checks approved Alter and restoration with the same GUID/MASTER ID and count.
Original company vouchers remain unchanged; master comparison allows only Tally's
automatic Purchase `PREVNARRATION` bookkeeping, not configured accounting fields.

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
