# Bill entry

Bill entry connects the shared desktop/web review to the registered Windows
companion and confirmed Source discovery context. The mock-client composition
installs it for `mock-tenant`; PR Infra does not. No customer rules or data are
added.
The existing hosted Agents API runs all Accounts proposals on `gpt-6-luna`;
launch rejects another model. The model never writes financial systems.

## Bill selection and settings

Select **Destination PC** before launching Bill entry from the web. The picker
lists this account's PCs, labels offline/expired registrations, and remembers the
choice per account/workflow in this browser. Multiple PCs require an explicit
choice unless a choice was already saved. A missing or expired saved PC never
switches automatically to another machine.

Discovery is loaded for that PC only. Tally company choices and Excel destination
catalogs come from its latest discovery; missing/incomplete discovery blocks launch.
Dashboard Quick Run retains the same PC even when another PC has newer discovery.
Changing the picker without launching sends Quick Run back to setup rather than
using its older target. A later folder rebind cannot reroute an approved Excel save,
and an explicitly PC-directed save cannot fall back to a browser folder.

Bill entry has one settings panel: its initial values are saved tenant defaults.
Edits apply to the current run; only workspace editors can persist them with
**Save defaults** or change workflow status. Catalog and company choices stay
contextual under **Destination and checks**. New Tally runs honor the selected
review mode. **Only exceptions** dispatches clean supported bills independently;
uncertain inputs stay in Attention. **All outputs** and client-wide review policies
retain explicit approval. Already-pinned legacy runs keep their original behavior.

Workflow 0.11.1 selects company/catalog-scoped master references with identity
evidence from full Discovery, including aliases and relevant native voucher history.
The server supplies canonical ledger names before business identity and monetary
validation; spelling, spacing and language differences alone do not force review.
Foreign, ambiguous, invented or stale references remain held. New supplier creation
requires an explicit positive lookup outcome and the existing operator decision;
an unresolved match is not a new supplier. Purchase classification excludes the
current invoice's own voucher as supporting history. Similar references retain
every token; similar dates or amounts alone do not establish duplicate identity.

Workflow 0.12.0 replaces free-text findings with typed exceptions. The model can
block a bill only with a code from a closed list of genuine blockers (unreadable
source, not a bill, unclear bill count, missing value, conflicting values,
unclear company or supplier, missing supplier, uncertain ledger, unsupported
structure). Everything else is a non-blocking internal note: successful checks,
absent optional values, and similarity to an existing voucher. Native
reconciliation alone decides duplicates. Attention labels come from the code.
Under Only exceptions, held bills are flagged in shared Attention. A file may
contain one bill plus copies and companion documents (e-way bill, IRN
acknowledgement, challan, PO); those corroborate a single record. Runs pinned to
earlier versions keep their free-text contract.

Workflow 0.12.1 closes three gaps found by the 39-bill paid evaluation. Supplier
identity must come from what the bill prints; when a printed name such as a
shared leading word fits two supplier ledgers, the bill is held as Supplier
unclear, because purpose and purchase history may choose an expense ledger but
never a creditor. Split CGST/SGST is checked against the run's capability flag
before any hold. Itemized goods posted to a ledger that the company's own
history books as plain accounting vouchers follow that practice rather than
being held for inventory. Workflow 0.12.2 validates a scanned GSTIN's check
character before comparing it: a read that fails the check is re-read as an OCR
error instead of being treated as a conflicting buyer.

Before any import, a bill dated before its company's Tally "Books beginning from"
date (collected in discovery's company identity) is held as **Before books
begin**. Tally cannot record such a voucher; Minkops never moves the source date.
Older discovery snapshots without the date skip this preflight.

The grouped file selector supports individual/group/all selection and search.
Selections persist in this browser by source ID and path, including an explicitly
empty selection. Refresh preserves choices when snapshot IDs change, removes
missing files and leaves new files unchecked. Upload cancellation submits nothing;
source loading failures offer a retry without overwriting saved choices.

Connected PCs shows device readiness independently of workflows. **Check
connections** opens the chosen PC's tool panel without submitting a job. Its
explicit **Check Tally connection** action uses the existing read-only
`tally.probe` job, owner checks, CSRF token and request key. Offline checks wait
for reconnection; expired PCs must reconnect first.

The browser regression suite uses synthetic sources and intercepts every API
request. It never runs a live Windows or Tally adapter. From
`apps/solution-web`, run `npm run test:browser` after installing Playwright's
Chromium (`npx playwright install chromium`). To use an existing Chromium,
run `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:browser`.
Screenshots and failure artifacts default to `/tmp/minkops-ui-tests`; override
with `MINKOPS_UI_ARTIFACTS`. Unit tests remain `npm test`.

## Workflow

### Exception review and export

### v1 settings and handler policy

New UI launches are Tally-only. Read bills groups the input format, Tally
destination groups discovery/company/voucher-type choices, and Review and save
groups review mode. Exact ledger/amount validation, duplicates and native
readback are mandatory. Excel/Both/draft and Excel-only checks are hidden in
v1; pinned legacy runs retain their adapters and recovery contracts.

The server owns the following maximum handler matrix. It further removes write
actions when mandatory values, company/master identity, source evidence or
supplier-creation prerequisites fail. Recheck appears only for an unresolved
input; saved/rejected/writing bills and runs outside review offer no decisions.
Best guess retains its separate human-review Attention after native save.

| Typed code | Maximum handlers |
| --- | --- |
| `source_unreadable` | Best guess write, Do nothing, Recheck |
| `classification_uncertain` | Best guess write, Do nothing, Recheck |
| `manual_review` | Best guess write, Do nothing, Recheck |
| `supplier_missing` | Create this ledger, Do nothing, Recheck |
| `not_a_bill` | Do nothing, Recheck |
| `multiple_bills_unclear` | Do nothing, Recheck |
| `required_value_missing` | Do nothing, Recheck |
| `source_values_conflict` | Do nothing, Recheck |
| `company_unresolved` | Do nothing, Recheck |
| `supplier_unresolved` | Do nothing, Recheck |
| `unsupported_structure` | Do nothing, Recheck |
| `date_before_books` | Do nothing, Recheck |
| `destination_changed` | Do nothing, Recheck |
| `voucher_type_unresolved` | Do nothing, Recheck |
| `identity_rule_unknown` | Do nothing, Recheck |
| `date_outside_company_period` | Do nothing, Recheck |
| `posting_profile_miss` | Best guess write, Do nothing, Recheck |
| `extraction_failed` | Do nothing, Recheck |
| `run_stopped` | Do nothing, Recheck (only after an active review) |
| `human_review` | Do nothing, Recheck; shared Attention has Done/Refresh |
| `company_not_open`, `no_company`, `duplicate_company` | Retry save, Do nothing |
| `not_running`, `port_closed`, `busy`, `too_many`, `invalid_response` | Retry save, Do nothing |
| `rejected`, `save_hold`, `save_held` | Retry save, Do nothing |
| `save_waiting`, `save_interrupted`, `pc_unavailable` | Retry save, Do nothing |

Unknown future codes offer only Do nothing/Recheck until a handler is explicitly
supported. The UI consumes server-derived actions and never infers eligibility
from free-text findings. Mark Done and Refresh remain shared Attention actions.

**Apply to all similar** is offered for Create this ledger, Retry save, Do
nothing and Recheck only when the server can identify a shared subject. New
suppliers group by company GUID, normalized printed name and GSTIN. Native save
holds group by company and typed hold reason; books-date and voucher-type holds
also have company-scoped subjects. Ambiguous suppliers/ledger pairs and Best
guess write have no bulk action in v1.

A fresh server preview shows the subject and count before confirmation. The
apply request is fenced to that cohort and revision: changed bills require a
new preview. All member audits and state changes commit together. One bulk save
uses one approval; one supplier group creates one native job, then continues
every still-matching, explicitly authorized proposal after readback. Other
pending writes do not strand a verified supplier continuation. Recheck refreshes
discovery once and creates independent bounded child sessions. Repeated requests
return the existing result without queuing another write or duplicating audit.

`attention_events.detail` stores a versioned decision record: company, code,
structured subject, action, actor, source/trigger item, proposal, count, stable
decision tuple and snapshot token. MIN-132 can reuse this record for client
memory; this release does not remember or automatically reuse choices.

### Exception sheet contents

Review lists only bills that Minkops has not successfully saved. Saved bills and
verified duplicates appear in a collapsed count ("saved · already in Tally").
Each remaining proposal or unresolved input has a plain-language sentence from
its typed exception or native save outcome, never from model findings. Do nothing
preserves that reason in durable deferred state and shared Attention.

**Export CSV** downloads the same server-owned projection in web and Windows.
It is available once results are combined and the run is in review, completed,
failed or stopped; processing and active saves disable it with an explanation.
`GET /api/tenants/{slug}/accounts/runs/{id}/unsaved-bills.csv` uses the run's
tenant authorization and private/no-store response headers. The UTF-8 BOM makes
Excel detect the encoding, and text cells are escaped against spreadsheet
formulas without changing negative numeric amounts.

The sheet contains source file, invoice, supplier, date, the proposed voucher
lines (`Ledger Dr/Cr amount`), total tax, gross total, company, status, reason
and Attention ID.
Statuses are **Needs attention**, **Save held**, and **Not written (Do nothing)**.
Saved and duplicate bills are excluded. Multi-bill PDFs have one row per bill;
inputs with no proposal have one file row. The open file-level bill Attention ID
is preferred, then the supplier ID; several bills may share that ID.

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

Business identity uses supplier, invoice number and the Indian April–March
invoice year (`accounts/vouchers.py` `invoice_year`): supplier serials are unique
within it, whatever financial year the buyer's books use. Excel otherwise uses complete confirmed
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

Approved plans keep the format they were approved in. A protocol-5 companion
(0.9.0+) receives each one as a v5 voucher (header plus balanced ledger lines,
see [Windows app](windows-app.md#companion-090-contracts)) searched within the
bill's invoice year; its receipt is verified against that upgrade and stored in
the usual observation shape. The invoice identity hash is unchanged, so vouchers
saved earlier keep their remote IDs and reservations. Plans without discovered
ledger and voucher-type GUIDs keep their original writer until they drain.
Refresh observes bills with the same reader as the save, so a reader change is
never mistaken for an edit made in Tally.

Pending writes reserve the workbook, or the company GUID and bill identity,
across runs and registered PCs. Confirmed Tally company/ledger identities and
versions are rechecked natively before saving. Each write requires exact saved
bytes or voucher/ledger/amount readback. Completion of one native job cannot
complete a batch with pending or held bills.

Consequential jobs are not automatically repeated after lease expiry. Explicit
Resume saves first reconciles the destination, handling an already applied write
without adding it again. Persisted receipts are replayed before another native
job. A save that finished but was refused or held by its destination returns
to review with Retry save, which re-sends the same proposal after the fix.
Cancellation releases pending reservations and preserves applied changes.
A late cancelled receipt records what was saved without restoring success or
rewinding newer observed workbook bytes. Independent external writers can still
race Tally's separate read/import calls: ambiguous matches or mismatched readback
require reconciliation, never a claimed successful save.

A provider stream that drops after the bill's turn started is reattached to
the same turn, up to three times, and its result read as usual; no session or
input is resubmitted. A failure before the turn exists is ambiguous, so the
bill stays unresolved for an explicit Recheck bill. While saves wait for the
destination PC, the run names that PC and asks to keep Minkops running there.

## Supported mapping

Excel uses actual confirmed headers, sheet/table boundaries and types; it does
not impose a universal invoice schema. Existing workbook protections, formulas,
styles, hash checks, native backups and atomic replacement remain in force.

From bill-entry 0.14 Tally has no fixed field list. The AI proposes the voucher
the client's own practice records for each document: the family (an invoice is
a Purchase or a Journal; a supplier credit note is a Debit Note), the voucher
type, the supplier and every other line (role, ledger, side, amount, optional
cost centre/category and tax head/rate/base), each selected by native GUID from
the routed company's pinned discovery (`accounts/vouchers.py` `check`). The
application only binds and proves it:

- every identity belongs to the routed company, is active where that matters,
  and every ledger is distinct; purchases use the run's chosen voucher type;
- the server computes the supplier line from the printed total, and debits must
  equal credits to the paisa;
- each tax line is within one rupee of its own printed rate × taxable value, and
  central and state halves of one rate and base are equal;
- at most one printed round-off of at most one rupee;
- cost centres must belong to the chosen category on a ledger that enables them;
- TDS waits for a confirmed posting profile; a foreign supplier holds
  (`identity_rule_unknown`), because only the Indian invoice year identifies a
  document;
- inventory, bill-wise allocations and foreign currency are connector limitations
  the AI reports as `unsupported_structure`, naming the structure.

**Posting patterns.** Each company's way of recording supplier documents is
derived once (the `posting_profile` stage reads that company's discovery only)
and stored as a versioned client profile. Code proves every identity it names;
a member confirms it once from the Attention card "Confirm posting pattern"
(**Confirm** / **Do nothing**), and the company's bills wait until then. Bills are
then checked against it: its voucher type per document kind, supplier party
groups, round-off ledger and cap, TDS ledgers with their section and rate
(deducted on the expense value), and where supplier document numbers are
recorded for duplicate checks. A bill that does not fit holds as
`posting_profile_miss`; three misses retire the pattern. A year-split sibling
inherits a confirmed pattern when every identity re-binds by exact name and
parent group, and newer discovery keeps a pattern while its identities and
groups still hold, so routine master edits never ask again. Concurrent runs
share one derivation; a failed derivation releases the company so its bills
hold and the next run derives again.

Approved bills are stored as native v5 plans (Windows companion 0.9.0+, see
[Windows app](windows-app.md#companion-090-contracts)) and reviewed through a
server-built preview of exactly those lines; `data` keeps only the document
summary (supplier, number, date, total, tax) that attention, policies and exports
read. Proposals pinned to 0.13 or earlier keep their fixed Purchase mapping and
writer until they drain (MIN-155). This accounting voucher contract does not
assert statutory filing readiness.

The adapter uses bounded fixed XML exports/imports on the PC's loopback port;
there is no renderer-supplied XML, URL, TDL or shell. Tally's documented correction
selector needs its original DATE and MASTER ID. References:
[Tally sample XML](https://help.tallysolutions.com/sample-xml/) and
[Tally voucher alteration](https://help.tallysolutions.com/scenario-2/).

## Synthetic companies and saves

Synthetic Tally companies, bills and expected outcomes for live checks come from
the [five-company rehearsal](tally-rehearsal.md); labelled packages are graded
with the fixture scorer described under Verification. Never point either at a
real client company.

Discovery is mandatory before dependent workflows, with manual refresh afterward.
Its date range applies only to vouchers; all masters are exported comprehensively.
No scheduling is introduced.

Bill saves run against the user's open Tally session; Minkops never starts or
restarts Tally. Before each save the run's company must be open and match the
discovered GUID; otherwise the bill holds ("Open company in Tally") and Retry save
continues once it is open. Reads may repeat after a timeout; an uncertain import is
never automatically resent. Read-only reconciliation distinguishes an
already-applied bill, a conflicting version and an absent bill requiring review and
Retry save. Native rejections are classified (date, permission, voucher type,
voucher number, ledger) into short labels; Tally's own text stays in diagnostics.
See [the Windows companion](windows-app.md).

Each run writes with a purchase voucher type pinned per company from discovered
masters (automatic when only one is active, otherwise chosen at launch), and checks
duplicates across every purchase-based type, including inactive ones; a matching
Journal voucher holds. Choosing "Use one company for this run" suits practices that
keep one Tally company per financial year. **Show details** on each proposal lists
the company, voucher type, date, ledgers and amounts it will enter.

## Verification

Offline tests replace the paid proposal boundary and exercise real PostgreSQL,
authenticated API transport and immutable financial plans. They cover
117/118/119 wiring, parallel sessions, isolated failures, duplicate uploads,
backfills, corrections, stale review, cross-PC reservations, receipt replay,
lease expiry, stopped tasks and late receipts. Native tests run on Windows and
Linux and include the Tally alteration selector regression. Shared UI build,
lint and web tests are run. The review shows concise identifiers and one-click
decisions; detailed evidence and logs remain internal (see [attention](attention.md)).
Live checks against real Tally companies use the
[five-company rehearsal](tally-rehearsal.md) and the labelled fixture scoring
below; see [the Windows companion](windows-app.md) for distribution limitations.

### Scoring and replaying labelled fixture packages

A fixture package holds `bills/*.pdf` and `evidence/expected-bills.json` with
the expected outcome of every input. Select only `bills/` as inputs.
`scripts/bill_entry_fixtures.py` grades a finished run per input as correct,
an unnecessary hold, a wrong reason, a wrong save or a missed exception. The
last two are critical and make the command exit nonzero. Use `--rerun` when
the inputs were already saved and every create should now be a duplicate, and
`--dry` for an All outputs run graded before saving. Educational Tally accepts
only voucher dates on the 1st, 2nd and 31st; a correct bill held solely for its
date passes.

`replay` processes a launched run with the answers a correct agent returns,
so everything after extraction is exercised on real documents without paid
sessions. Stop the normal worker first; replay claims only the named run.

```sh
uv run --all-packages python scripts/bill_entry_fixtures.py replay RUN_ID packages/<package>
uv run --all-packages python scripts/bill_entry_fixtures.py score RUN_ID packages/<package> [--dry|--rerun]
```

### GST supplier creation (0.13 / Windows 0.8)

Create this ledger requires printed GSTIN, registration type, state, place of supply, address and PIN with literal page evidence, deterministic checksum/state validation, and a compatible registered supplier template in the same confirmed company. Existing GSTIN aliases, missing evidence and cross-state creation require manual handling in v1. Older pinned runs retain their prior behavior. The native callback must verify every approved statutory and mailing field before a bill is queued; an import acknowledgement alone is insufficient.
