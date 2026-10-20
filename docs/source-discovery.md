# Source Discovery: reusable client context

Source Discovery 0.8.2 and Windows companion 0.6.6 collect a versioned package
before Bill Entry can run. Refresh is manual. Existing schema-only catalogs stay
readable, but a new Tally bill run requires a complete, confirmed version 2
package from its connected PC. No scheduled collection is introduced.

## Review and progress

Setup keeps PC selection, source choice and the voucher date range compact.
Results use searchable company/folder rows, eight per page, with master totals
and counts by type; record names remain in the saved catalog. Unique master
counts come from the existing server lookup summary. Older exports without that
summary are explicitly labeled exported masters, rather than claiming uniqueness.

The four checkpoints distinguish waiting, active, done, required input and stopped
states. A phase meter measures verified native reads (company identity, full
master export, voucher date chunks and final scope check) or inspected workbooks.
One activity line replaces its previous text. Failed exports never advance the
count, and the meter is not an ETA or permission to reuse a catalog. Hosted
interpretation and older companions without measurements show indeterminate
activity. Only verified catalog confirmation marks the workflow finished.

The optional bounded `progress` object travels through the existing companion
observation endpoint. Measurements replace durable observation state without a
task event per export chunk. Roll out the API accepting this optional field
before a companion that sends it; older companions remain supported. Transient
browser poll failures preserve the last results, show interrupted updates and
retry with bounded backoff. Motion respects the reduced-motion preference.

## Collection and interpretation

Each run has an **AI context analysis** toggle, on by default. The optional
`ai_context` collection-config boolean defaults to true for older callers.
When off, native Tally masters/vouchers and deterministic Excel structure are
still collected and saved, but no hosted run is dispatched. Complete results go
directly to review and still require confirmation. Excel structure-only catalogs
have no new semantic column mappings or Bill Entry destination catalog; they
cannot supply a new Excel entry destination. The prior run's toggle is restored
by setup and preserved by quick refresh. Partial/oversized collection safeguards
and downstream input limits remain enforced. This option never samples records
or silently reuses interpretation from an AI-enabled run.

Source Discovery always uses `client_context`; depth and category selectors are
removed. The upgrade migration removes retired depth settings from installed
workflows while preserving immutable historical run catalogs.

Tally discovery reads **the companies the user has open in Tally**, from any data
folder. Minkops never starts, closes, restarts or locates Tally, never handles
company passwords and never chooses data folders: the user opens the companies
(entering passwords in Tally) before discovery. `Company on Disk` is not read; it
covers only the single folder named by `tally.ini` and misleads in practices that
keep companies in several folders.

The GUID identifies a company. Company numbers are folder-local (every folder
numbers from 100000) and are display data only. Two open companies with the same
name block discovery with one action, because every native request selects its
company by name. Snapshots use format 3 for this open scope; format 2 catalogs
remain valid. The package becomes partial if companies are opened, closed or
replaced during collection, and a Tally that closes mid-run ends the run with its
typed action instead of failing each remaining company. A partial package cannot
be confirmed or reused as complete context.

Review compares the run with the previous confirmation on the same PC and names
companies **No longer included** and **Newly included**. A smaller scope is the
user's choice: confirming accepts it, and bills for a removed company wait until
it is opened and discovered again.
The fixed connector accepts a loopback port and inclusive voucher period, never
caller XML, TDL, scripts, hostnames or SQL. ODBC metadata discovery is removed.

For each company it exports full identity, native **List of Accounts** with **All Masters** and no date
filter, and full native voucher collections in 31-day date chunks. A fixed
calendar-component predicate preserves the inclusive period even when native Date
variables are coerced; ledger and inventory allocation aliases are fetched explicitly.
Native nested
fields, custom master types, identifiers and leading zeroes remain intact.
Collection never samples records. Date filters apply only to vouchers. The collection
identifiers follow [Tally’s XML samples](https://help.tallysolutions.com/sample-xml/);
**All Masters** alone is an import report.
Installation-specific customisations and counts require native export comparison;
live checks have covered UDF and batch preservation, inclusive periods and empty
exports.

The hosted discovery skill inspects those saved records and proposes only obscure
conventions or exceptions as subjective notes. Each note identifies its company,
actual collected master/voucher evidence and whether it is observed or inferred.
Notes may be empty. Routine vendor/item relationships remain in the actual voucher
files for later lookup, rather than becoming hundreds of prose rules. Confirmation
validates note references and accepts the package and any Excel mappings.

Confirmation authorizes the company scope, Excel structure and approved meanings,
and the configuration. A later refresh with the same authority reuses it
automatically, even when vouchers or masters changed, including vouchers Minkops
saved. Confirmed notes are re-validated against the new collection, and a note
whose evidence disappeared requires review again. A changed company identity or
scope, Excel layout or configuration still needs confirmation. Catalogs confirmed
before this rule used a fuller fingerprint, so their first refresh asks once. If optional AI context analysis fails for a Tally-only
collection, the complete native sources can still be confirmed without notes;
that confirmation closes the failed analysis's attention item with an audit.

Excel discovery projects selected `.xlsx` workbooks into fresh packages containing
sheets, table/header definitions and formula text. Cached formula results,
business rows, comments, links, images and named constants are excluded. Formula
text may itself contain literals; it is part of the authorized structural input.
Formulas are never evaluated. Plain-sheet header candidates require review.
Formula/layout changes invalidate automatic reuse of the mappings. Unsupported
formula representations or collection failures require attention.

## Persistence and downstream access

Raw native exports remain immutable in PostgreSQL and the PC archive. Newly
collected or pinned catalogs carry `master_lookup_version: "1"`. Downstream
files are a derived view: verified remote-company trailers are separated and
identical records with the same company/type/native identity are collapsed.
Conflicting definitions for one identity block lookup preparation. Every retained
record has `source_record_indexes` pointing into its company's raw master export.
Statutory/default masters and custom types remain available; counts are not fixed.

Each company manifest supplies `master_lookup_path`: an index grouped by type,
GUID and exact name, with candidate lists containing file paths and zero-based
offsets. Equal names with different GUIDs remain separate candidates; companies
are never merged. `TAXUNIT` definitions remain available for buyer GST identity.
The UI shows unique counts by type and distinguishes raw exported records,
duplicates and metadata. Already-pinned catalogs without the lookup version retain
their original file contents and hashes. No new DB table, live retrieval endpoint
or accounting state is introduced; hosted input-size limits still apply.

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

Native Tally collection supports 1–50 open companies, a period up to 3,660 days,
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

Typed Tally session states, diagnostics and uncertain-import reconciliation are
shared native capabilities; see [the Windows companion](windows-app.md).

## Pause, resume and stop

The operator can pause/resume or stop an active run from its task page. Controls
are shared with Bill Entry, installed proposal workflows and local jobs. Pause
blocks subsequent dispatch and approval; native discovery waits between verified
reads and keeps its claim alive. A hosted turn or destination save already underway
may finish. Its result and receipt remain authoritative. Resume wakes the cloud
worker and continues the existing durable run without resubmitting paid inputs.

Stop is irreversible: queued work and unsaved plans are cancelled, while completed
saves and late verified receipts remain recorded. Business items that still need
handling stay in shared attention. Explicit attention refreshes can still verify
the original destination. A stopped task cannot approve writes or become active
because an old receipt arrives. Start a new run for further automation.

Deploy migration `0004_task_execution_controls` with the API and hosted worker,
then the web client and companion together. Older companions honor dispatch gates
but cannot pause discovery between reads; their current collection may finish.
Polling exposes company/count summaries; full records remain in downloads and
the immutable execution package.

## Many companies

Bill Entry routes each bill to one company before posting (a short triage stage
over a compact company directory), so each posting session receives only that
company's masters, never sampled, and as much of its history as fits, with the
supplier's own vouchers first; the manifest records any history cut
(`vouchers_from`). Companies sharing a GSTIN are year-split siblings: each
sibling's period ends the day before the next one's books begin, and a bill dated
in a sibling's period is routed there deterministically with a note.

When every company together exceeds one hosted interpretation session, a
Tally-only collection stays complete and confirmable; only the optional client
notes are skipped (`ai_context_skipped`). Collections that also need an Excel
mapping session still hold until the scope is reduced.
