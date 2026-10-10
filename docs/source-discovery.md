# Source Discovery: reusable client context

Source Discovery 0.7.0 and Windows companion 0.5.0 collect a versioned package
before Bill Entry can run. Refresh is manual. Existing schema-only catalogs stay
readable, but a new Tally bill run requires a complete, confirmed version 2
package from its connected PC. No scheduled collection is introduced.

## Collection and interpretation

Tally discovery lists every company currently loaded through the local HTTP
service; it is independent of Bill Entry's company choice. Load all companies
that should be available before discovery. The fixed connector accepts a
loopback port and an inclusive voucher period, never caller XML, TDL, scripts,
hostnames or SQL. ODBC is no longer required for this core path.

For each company it exports full identity, native **List of Accounts** with **All Masters** and no date
filter, and detailed **DayBook** vouchers in 31-day date chunks. Native nested
fields, custom master types, identifiers and leading zeroes remain intact.
Collection never samples records. Date filters apply only to vouchers. The report
identifiers follow [Tally’s XML samples](https://help.tallysolutions.com/sample-xml/);
**All Masters** alone is an import report.
Cancelled/optional voucher coverage, customisation completeness and counts must
be verified on the actual installation before release; native export support is
not established by an offline fixture. See
[MIN-124](https://linear.app/minkops/issue/MIN-124).

The hosted discovery skill inspects those saved records and proposes only obscure
conventions or exceptions as subjective notes. Each note identifies its company,
actual collected master/voucher evidence and whether it is observed or inferred.
Notes may be empty. Routine vendor/item relationships remain in the actual voucher
files for later lookup, rather than becoming hundreds of prose rules. Confirmation
validates note references and accepts the package and any Excel mappings.

Excel discovery projects selected `.xlsx` workbooks into fresh packages containing
sheets, table/header definitions and formula text. Cached formula results,
business rows, comments, links, images and named constants are excluded. Formula
text may itself contain literals; it is part of the authorized structural input.
Formulas are never evaluated. Plain-sheet header candidates require review.
Formula/layout changes invalidate automatic reuse of the mappings. Unsupported
formula representations or collection failures require attention.

## Persistence and downstream access

PostgreSQL holds the tenant/operator/device-scoped immutable catalog and reviewed
notes. The connected PC also creates atomic, hashed packages under its per-user
Minkops app-data directory: `discovery/<tenant>/collected/<run-id>` immediately,
and `discovery/<tenant>/confirmed/<run-id>` after confirmation. While connected,
it archives every confirmed version in order, including versions confirmed while
it was offline. Each directory contains `manifest.json`, `catalog.json`,
`context.json`, and separate company masters/voucher JSON files. Local files are
restricted to the user's account; credentials and folder grants remain encrypted
separately. A visible Connected PCs error reports an archive failure.

The server copy is intentional: it reuses durable storage, access controls and
hosted file delivery rather than adding a second synchronization system. No DWH,
accounting ledger or balance model is introduced. Optional catalog JSON export
remains available through the existing Save As flow.

Bill Entry pins the confirmed package at launch. A compact manifest supplies
company identities and lookup paths; full masters and vouchers enter authorized,
immutable JSON input files, split at record boundaries. They need not remain in
the model's conversational context. The existing Purchase mapping supplies a
bounded extraction schema and its prompt explains field meanings. Bill Entry
performs no discovery or reference export of its own. Native writes still check
current company and master identities immediately before import.

## Bounds and failure behavior

Native Tally collection supports 1–50 loaded companies, a period up to 3,660 days,
32 MB per HTTP response and 64 MB overall collection/validated snapshot. Excel
retains 5 MB/workbook, 100 sheets, 10,000 rows, 500 columns, 250,000 cells/sheet
and 50 MB expanded ZIP bounds. These are parser limits, not permission to upload
business rows.

The existing hosted input budget remains 45 files / 8 MB combined, including
lookup JSON and bills, with 4 MB per file. Oversized complete exports remain
saved, but interpretation is visibly partial and dependent workflows are blocked.
Reduce the voucher period or hand off when masters alone exceed the budget;
masters must never be sampled to fit. Partial company collection preserves the
successful data but cannot authorize Bill Entry.

Legacy pinned runs retain their original contract, including their old reference
preparation path where applicable. New runs use version 2. Retry may adopt a
newer confirmed package on the same PC only if the discovered company GUID set
is unchanged. Completed sibling entries retain their receipts and plans.

Tally error diagnosis, bounded restart and uncertain-import reconciliation are
shared native capabilities; see [Windows recovery](windows-app.md).
