# Accounts desk rebuild

This is the handoff for rebuilding Bill Entry and Statement Entry from scratch,
agreed on 21 October 2026. It records every decision so far and how to carry
on from another machine. The evidence behind each decision is in
[evidence.md](evidence.md).

## Where things stand

- **This branch, `accounts-desk/rebuild`, starts from `maintenance/retire-legacy-paths`.**
  - That branch removed every legacy path: the fixed-field bill contract, the Excel bill destination, plan protocol 4, guessed runtime bindings, and the launch voucher-type picker.
  - Migration `0019` stops unfinished runs that still depended on those paths.
  - Source shrank by 10.7%, and the Accounts package by 26%.
- **`platform/workflow-reliability` is left untouched and will most likely be discarded.**
  - The state before the retirement is commit `2781c60`, an ancestor of this branch, so it stays reachable after that branch is deleted.
  - A local tag, `archive/2026-10-21/before-legacy-retirement`, exists only on the original Mac.
- **The build is under way.** [Progress](#progress) records each slice's state and evidence; [design.md](design.md) maps the modules, tables and protocols.

## Continue on Windows

**Do this before cloning.** The repository has no `.gitattributes`, and CRLF line endings change the bytes that migration checksums and the archived-migration hashes in `db/tests/test_branch_upgrade.py` are computed from:

```powershell
git config --global core.autocrlf false
git clone git@github.com:minkowski-home/minkops-ai.git
cd minkops-ai
git switch accounts-desk/rebuild
```

Adding a `.gitattributes` (`* text=auto eol=lf`) is a good first commit.

**Tools you need:**
- `uv`, which manages Python 3.12 (see `.python-version`);
- Node 24;
- Docker Desktop, for PostgreSQL 16;
- TallyPrime Educational, for rehearsals.

**Set UTF-8 mode in every shell.** On Windows, Python 3.12 otherwise reads files as cp1252, and the docs and skills contain characters such as `→` and `₹`.

```powershell
$env:PYTHONUTF8 = "1"
uv sync --all-packages
docker run -d --name minkops-test-pg -e POSTGRES_PASSWORD=<choose-one> -p 5434:5432 postgres:16
$env:TEST_DATABASE_URL = "postgresql://postgres:<choose-one>@127.0.0.1:5434/postgres"
$env:AUTH_DEV_MODE = "1"
uv run --all-packages pytest platform/tests apps/solution-api/tests connectors/tests db/tests apps/corporate-website/api/tests infra/tests scripts/tests -q
uv run --all-packages ruff check .
```

Pytest creates and drops its own database on that server; see [isolated integration tests](../../db/README.md#isolated-integration-tests). Then the companion and web checks:

```powershell
cd apps/windows-app; npm ci; npm test; npm run build
cd ../solution-web; npm ci; npm test; npm run lint; npm run build
```

`npm run package:win` (in `apps/windows-app`) builds the installer. See [Windows app](../windows-app.md#build-and-run) for publishing.

**Baseline on this branch** (macOS, 21 October 2026): 617 Python tests, plus 413 subtests; 108 companion tests; 51 web tests; ruff, lint and both builds clean. The Playwright browser tests, a live companion run against Tally, and a production restore rehearsal have not been run.

**Working from WSL 2** (how this build was done): keep the checkout on the Linux filesystem, which keeps LF endings, and run TallyPrime on Windows. The companion's adapters address Tally at `127.0.0.1`, so relay it into WSL first:

```bash
python3 scripts/wsl_tally_forward.py
```

Then check that the five rehearsal companies are open with their pinned GUIDs:

```bash
node scripts/rehearsal_status.mjs
```

PostgreSQL 16 can run from PGDG packages extracted into the user's home without root; Node 24 can run from the official tarball. Package the Windows installer from a Windows-local copy, because WSL symlinks break the packaging tools.

**Sample client files are not in git.** One ICICI statement for September 2026 and two scanned March 2026 bills were shared on 21 October; copy them to the Windows machine yourself. Keep real files in a private, encrypted fixture store, and commit only synthetic look-alikes.

## Working agreements

These come from the original machine's assistant memory and from `AGENTS.md`:

- Excel is retired as a bill destination for good. It is no longer part of the Bill Entry workflow.
- Open or merge PRs only when explicitly asked, and only into `staging`.
- Before any merge into `staging`, park and push a `backup/staging-pre-<issue>` branch.
- Never mention tool or assistant attribution in commit or PR messages.

## Decisions

### Kept, non-negotiable

- **Identity.**
  - Bill identity is supplier, printed number and the Indian April–March invoice year, pinned by the golden hashes in `platform/tests/test_vouchers.py`.
  - Statement row identity is `row_identity` in `connectors/src/minkops_connectors/statement.py`: reference, date, amount, balance and occurrence.
  - Narration tokens are `uuid5("minkops:{tenant_id}:…")`.
- **Write safety.**
  - Record a durable intent before import.
  - Never resend an uncertain import.
  - Reserve each company GUID and bill.
  - Recheck masters by GUID and AlterID before a save, and require an exact readback after it.
  - Keep the Stop and late-receipt semantics.
  - Use only fixed native operations.
- **The Windows companion (`connectors/desktop/src`) stays as it is**, apart from the additions below.
- **Accounting judgment.**
  - The printed supplier decides supplier identity.
  - Holds use a closed list of codes, and the server owns which actions each code allows.
  - Check the GSTIN check character and the books-beginning date.
  - Never sample masters.
  - Prove statements against their balances.
  - Posting patterns are derived, confirmed, reused, and retired after three misses. The rebuild keeps them as memory entries, confirmed by use (Structure 5 and 7).
- **Product principles.**
  - One-click decisions, with no value editor.
  - Done and Refresh must rest on evidence.
  - A best-guess save stays under review.
  - **A failed check must say so; it never silently drops an action.**

### Structure

1. **The server schedules; it never sequences reasoning.**
   - Each bill, or each chunk of statement rows, gets its own session, and sessions run in parallel.
   - Company routing and practice questions are answered by lookups inside that session.
   - Results stream out as each one finishes.
   - There is no triage stage, no posting-profile stage, and no merge wait.
2. **Sync replaces Source Discovery as a workflow.**
   - The server keeps a mirror per PC and company: every master, plus vouchers synced incrementally.
   - A workflow declares only which voucher families and periods it needs, and how fresh they must be.
   - The sync never uses AI and never authorises a write.
3. **Mirror versions.**
   - Rows carry `synced_in` and `superseded_in`, and a run pins one version number. Nothing is copied into runs.
   - Scheduling state lives in its own table, never in run JSON.
4. **Two workflow layers.**
   - **Core workflow** (`employees/accounts-desk/workflows/<wf>`) holds only rules that generalise.
   - **Client-specific workflow** (`solutions/<client>/employees/accounts-desk/workflows/<wf>/`, through `variant.json` and `client-instructions.md`) holds procedure written with the client, reviewed in the repo and built on top of core.
   - Nothing client-specific goes into core.
5. **Employee memory.**
   - It is runtime data, not a workflow layer: kept per client business and per employee, shared by all of that employee's workflows.
   - It is looked up only when needed, never loaded into context up front.
   - An admin edits both of its parts, per employee.
   - **Structured part:** contract-like key-values, learnt from the one-click options offered during errors and ambiguities, and from outcomes that were both verified and accepted.
     - An edit made in Tally demotes an entry.
     - Entries carry their evidence and the GUIDs they refer to.
     - They are revalidated on every sync, re-bind to year-split siblings, and retire after three misses.
   - **Unstructured part:** plain-text instructions that are only ever stated by people, never inferred or learnt. They are scoped and versioned, and proposals cite them by ID.
   - **Practice probes and practice questions.**
     - The sync runs deterministic probes over the mirror. Examples: are Receipt Notes in use; do narrations carry receipt-register numbers; are bank payments booked to individual party ledgers or to one ledger with cost centres.
     - A probe that settles the question becomes a structured entry.
     - An inconclusive probe raises one one-click question per company, and the chosen option becomes a structured entry.
     - **No question ever blocks a run.** Only the bills that depend on it hold, and answering releases them through the same idempotent decision path as every other decision.
6. **Precedence.**
   - On **facts**, the printed bill wins.
   - On **treatment**, the order is:
     1. a legible handwritten instruction on this bill (an unclear one holds, and the note is shown);
     2. unstructured instructions;
     3. structured entries;
     4. native history.
   - Tally masters and the server's checks are hard constraints that no tier can override. Every override is recorded.
7. **Confirmation by use** replaces the "Confirm posting pattern" card. A bill that relies on an unconfirmed entry goes to review, and one approval confirms the entry.
8. **Lookups are function tools.**
   - The session reports `requires_action`; the worker answers with `agent.session.input.tool_result`. Pending calls survive in `AgentSession.required_actions`, so a restarted worker answers them on reattach.
   - Tools are read-only, scoped to the run, logged, and accept lists of subjects.
   - They are shaped like MCP, so they can later be served as a remote MCP server.
9. **`propose` tool.**
   - The server checks each proposal immediately.
   - The agent gets at most two resubmissions.
   - Any resubmission that changes printed facts is flagged for review.
10. **Plumbing.**
    - Three settings layers: the workflow definition, client policy and client memory.
    - One review surface for every workflow.
    - Decisions are idempotent per actor, item and version.
    - Wake-ups come from committed events.
    - Status responses stay small.
    - No dispatch on every request.

### v1 scope

- **Tenancy is designed for both** single businesses and accounting practices: tenant → client business → company, with per-client access.
- **Company lookup searches every GSTIN a company has.** The sample bills route to a state registration different from the one tied to the bank account.
- **TallyPrime only.** The companion reports the version it finds.
- **Tally may run on the accountant's PC or on a hosted cloud/RDP server.**
  - The installer is already per-user, and the Tally port is already set per PC.
  - Still needed: a signed installer and a checklist for hosting providers.
  - On a multi-user host, each Windows user counts as a separate PC.
- **The mirror lives on our server**, in a dedicated Cloud SQL (PostgreSQL 16) instance created at the fresh start. This is for isolating client books and for connection headroom, not for speed.
- **Fresh start, with new tenants.**
  - Bills are unaffected.
  - Statement rows that overlap earlier saves hold as `possible_existing`, so nothing double-posts.
  - PR Infra statements resume after the old build's last saved period.
- **Bill-wise references.**
  - A bill on a bill-by-bill ledger records a New Ref equal to the supplier's invoice number.
  - A payment settles its open bill with Agst Ref.
  - Partial, multi-bill and net-of-TDS payments get one-click buttons for the candidate bills.
- **Inventory.**
  - Items with quantity, rate, unit and godown are in, including multiple godowns.
  - Batches and order or receipt-note tracking hold, each with a named reason.
  - If the receipt-register probe or its question shows Receipt Notes are in use, receipt-note tracking moves into scope.
- **The first sync covers the current and previous financial years**, then runs incrementally.
- **Statements are CSV and XLSX only.**
- **Targets.**
  - 50 bills from launch to all proposed in 10 minutes: about 2 minutes per bill across 10–12 lanes.
  - A month of about 1,250 statement rows proposed in 15 minutes, in chunks of about 100 rows. This one is a default, open to review.

### Defaults, open to review

- **Memory editing.** Only admins edit memory, per employee. Each client gets a memory page showing the structured part as key-values with their evidence, and the unstructured part as plain text. Either can be disabled or deleted.
- **AI provider.** The OpenAI hosted Agents API (`gpt-6-luna`), used only through `runtime/openai_hosted.py`. Skills stay provider-neutral.
- **Same repository.** New modules sit beside the old ones, and each old module is deleted once a slice replaces it.
- **Sync timing.** A sync probe runs before each run, and in the background while the companion is idle.
- **Unrecognised masters.** A missing stock item holds. A newly seen company raises one card to authorise it.

## Client-specific knowledge from the PR Infra samples

This belongs in PR Infra's client-specific workflows and memory, never in core:

- **Receipt-register stamps.** Bills carry a receipt-register ("DMR") stamp, and the file names start with that number. How DMR is recorded in Tally is unknown; a probe or a practice question will settle it.
- **Site codes.** The statement's remarks field carries site codes, and bills carry handwritten site notes such as "DBM Plant Direct".
- **Bulk NEFT batches** go to many individual payees. How these are booked is unknown; a probe or a practice question will settle it.
- **Large receipts come from a related company.**
- **NEFT returns: book both legs.** This is seeded as an unstructured instruction in PR Infra's Accounts desk memory, which an admin can edit or remove.

## Sync algorithm

Items marked † must be verified in the TallyPrime rehearsal; sources are in [evidence.md](evidence.md#tally-incremental-sync-research).

1. **Identify each company** by PC, GUID, company number, name and BooksFrom, never by GUID alone, because Split Company GUIDs are uncertain†. Also fix the companion's duplicate-GUID message, which names the wrong company.
2. **Probe** `$AltMstId`, `$AltVchId`, `$LastVoucherDate` and `$BooksFrom`. Treat an empty AltVchId as 0. Stop if nothing changed.
3. **Regression guard.** If a marker drops, or the identity or BooksFrom changes, rebuild in full into a new version.
4. **Delta.**
   - Read the markers first.
   - Fetch masters and vouchers with `$AlterID` greater than the stored values.
   - Fetch vouchers in date batches of at most 5,000, sized by per-date counts.
   - Keep cancelled, optional and post-dated flags†.
   - Upsert by GUID, and commit the markers last.
5. **Deletion sweep**, whenever markers move and nightly.
   - Compare a per-date census of GUID and AlterID with the per-date counts.
   - A missing GUID becomes a tombstone, and a changed one is refetched.
   - **Never record a deletion when the census and the counts disagree.** A truncated response can still report `STATUS=1`.
6. **Auto-numbered voucher types:** during the sweep, re-pull each voucher's number by GUID.
7. **Practice probes** run after each sync, as SQL over the mirror.
8. **Send Tally one request at a time**, with long timeouts. An abandoned request still keeps Tally busy. Don't rely on the Edit Log or `ISDELETED`.
9. **The run's "Get ready" step waits** for the probe and delta. An offline PC, a closed Tally or a missing company shows as a named blocker.

## Lookup tools (v1)

- **Companies and ledgers:** `find_company` (by any GSTIN or name), `find_ledger` (by name, GSTIN, alias or bank account), `ledger`, `voucher_types`.
- **History and open bills:** `party_history`, `open_bills(party)`.
- **Stock:** `find_stock_item` (by name, part number or HSN).
- **Statement pairing:** `pair_return(utr)`.
- **Memory:** `memory(subjects, kinds)`, `rules(subjects)`, `practice(company)`.
- **Proposals:** `propose`.

Every tool accepts a list of subjects.

## Writer: plan protocol 6

- **Protocol 6 adds two things to v5:**
  - bill allocations (New Ref and Agst Ref);
  - inventory entries (item, quantity, rate, unit and godown, with their accounting allocation).
- **Readback** must cover every allocation and inventory line.
- **Duplicate strategies and fences** are unchanged.
- **Minimum companion:** protocol 6 ships with companion 0.10.0, which becomes the minimum version.

## Build slices

Each slice works end to end against a real TallyPrime company before the next one starts.

0. **Acceptance harness.**
   - Golden bill hashes and the code-to-actions matrix test.
   - The 39-bill labelled fixtures, with the `scripts/bill_entry_fixtures.py` scorer extended to report timing.
   - The [five-company rehearsal](../tally-rehearsal.md).
   - The tests the [runtime review](../reviews/2026-10-21-bill-entry-runtime-review.md) found missing: confirming after the worker has drained, losing the response after a commit, and the same decision sent twice.
   - Private PR Infra fixtures, with synthetic copies in the repo.
1. **Foundation.**
   - The dedicated database instance.
   - Tenant, client business and company, with per-client access.
   - Run and scheduling tables.
   - Event wake-ups and small status responses.
2. **Sync and mirror,** with versions and practice probes. Rehearse the † items: split companies, cancelled and optional vouchers, deletions, and feature fields.
3. **Session tool loop** in `openai_hosted.py`.
   - Answer `requires_action`, including after a reattach.
   - Log every tool call.
   - Run asynchronous lanes with a small memory footprint.
4. **Statement slice.**
   - Learnt XLSX and CSV layouts, reusing `statement_layouts` and the balance proof in `statement.py`, including the footer totals and the metadata that identifies the bank ledger.
   - Chunked row proposals, checked by `validated_plan`.
   - NEFT-return pairing.
   - Save and readback.
   - A re-run finds duplicates, and an interrupted save never writes twice.
5. **Bill slice.**
   - Read the scan.
   - Look up the company across all its GSTINs.
   - Consult memory, practice and history.
   - `propose`: the `vouchers.check` logic plus a check for tax-inclusive line amounts.
   - Handwritten instructions and confirmation by use.
   - Save and readback.
6. **Memory, rules and practice questions.**
   - Accepted outcomes become entries, and edits made in Tally demote them.
   - The admin memory page and the question cards.
   - The PR Infra client-specific workflow and its seeded instruction.
7. **Bill-wise link.**
   - New Ref on bills, the `open_bills` lookup, and Agst Ref on payments.
   - Candidate-bill buttons.
   - Protocol-6 allocations with readback.
8. **Inventory.**
   - Item lines and godowns.
   - Holds for batches and orders, or receipt-note tracking if the probe calls for it.
   - Protocol-6 inventory readback.
9. **E-invoice QR check** (feasibility first).
   - Decode the signed QR and verify its signature.
   - Pin supplier, buyer, number, date and total from it.
   - A conflict with what was read from the scan holds the bill.
10. **Review surface and Attention per client,** with a query cache and cancellable reads.
11. **Hosted Tally.**
    - A signed installer.
    - A check on multi-user hosts.
    - The provider checklist.
12. **Performance.**
    - Run 10–12 lanes.
    - Benchmark both targets, then tune.
13. **Cut-over.**
    - Create fresh tenants; PR Infra statements resume after the old build's last period.
    - Park the old build with a tag and a reproducible deploy.
    - Delete the old modules.

## Reused code

- **Companion:** `connectors/desktop/src/voucher.js`, `tally.js` and `tally-session.js` (the writer, Tally sessions and guards), plus `client-context.js`, whose collection became the sync (`sync.js`).
- **Statement reading:** `connectors/src/minkops_connectors/statement.py`.
- **Accounts checks** (`platform/src/minkops_platform/accounts/`): `vouchers.py`, `statement_layouts.py`, `validated_plan` in `statement_routing.py` and `supplier_gst.py`. `tally_writes.py` and `posting_profiles.py` were retired with the staged pipeline; the checks of theirs that still apply live in `vouchers.py` and `writes.py`.
- **Platform:** `attention.py`, `run_controls.py`, `desktop.py` and `runtime/openai_hosted.py`.
- **Workflow installation:** `minkops_api.install_workflows`, with variants.
- **Infrastructure:** `infra/provision_database.py`, `deploy_runtime.py` and `verify_database_restore.py`.

## Verification

- **Automated tests.**
  - pytest against real PostgreSQL.
  - Node tests for the companion.
  - Playwright for the review surface.
- **TallyPrime rehearsal** covering:
  - duplicates and interrupted saves;
  - split companies and deletions;
  - cancelled and optional vouchers;
  - bill-wise settlement and inventory readback;
  - NEFT returns.
- **Scoring.**
  - Zero critical outcomes, meaning no wrong saves and no missed exceptions.
  - Both performance targets met.
  - The PR Infra fixtures pass.
- **Restore rehearsal** on the new database instance.

## Risks

| Risk | Handling |
| --- | --- |
| Tally IDs or markers behave unexpectedly | Regression guard, census guard, the † rehearsal |
| A wrong memory entry spreads | Learn only from approvals; edits made in Tally demote; a removable memory page |
| Questions stall work | Hold only the dependent bills; release them through the idempotent decision path |
| Prompt injection through bills or narrations | Read-only, scoped tools; every call logged |
| The agent argues past a check | Resubmission limit; changes to printed facts go to review |
| Crumpled or low-quality scans | Hold with a reason; the QR check where available |
| Provider concurrency limits or cost | Measure in slice 12 and revise the cost envelope |
| Retaining mirror data (India's DPDP Act) | Retention and deletion policy before production |
| Large first syncs | Background sync with visible progress |

## Pending (doesn't block starting)

- A PR Infra statement covering the March 2026 payments for the two sample bills: the client's own fixture for the bill-to-payment link, which slice 7 rehearsed on synthetic books.

## Progress

Built on Windows through WSL 2 (Ubuntu 26.04) against TallyPrime Edit Log 1.1.7.2 in Educational mode, from 21 October 2026. The baseline before any rebuild commit: 617 Python tests plus 413 subtests on PostgreSQL 16.15, 108 companion tests, 51 web tests, with lint, ruff and both builds clean.

| Slice | State | Evidence |
| --- | --- | --- |
| 0. Acceptance harness | Done | One closed hold matrix pinned by a golden test (`test_holds.py`). Golden bill, statement-row and narration-token identities (`test_vouchers.py`). Synthetic look-alikes of the PR Infra statement and bills, with private-file structure checks (`test_synthetic_fixtures.py`). The five-company rehearsal is verified live (`scripts/rehearsal_status.mjs`). The runtime review's missing tests land with slice 1's decision path, and scorer timing with slice 5's bill runs. |
| 1. Foundation | Done | Code and tests provision the dedicated instance (`test_database_provisioning.py`); it has not been created or deployed. Client businesses, per-client access and company identity are in migration `0020` (`test_clients.py`). The run model is in migration `0021`: leased items, versioned records, idempotent decisions, commit-time wake-ups and bounded status (`test_work.py`, `test_runs_api.py`). That includes the runtime review's missing cases: confirming after the worker drained, a response lost after commit, and the same decision twice. 663 Python tests pass. |
| 2. Sync and mirror | Done | The versioned mirror, the sync protocol with its regression and census guards, practice probes and background refresh (`test_mirror.py`, `test_sync.py`, `test_practice.py`, `test_sync_api.py`, `sync.test.js`, `jobs.test.js`). Rehearsed live through the headless companion: all five companies were found, authorised and mirrored in full in 14 s, matching Tally's own voucher counts and seven master types exactly. A created voucher arrived as a delta, a cancellation as a flag, and a deletion as a census tombstone ([evidence](evidence.md#rehearsed-on-tallyprime-edit-log-1172-21-october-2026)). Source Discovery is replaced by the sync; it is deleted with the staged bill and statement pipelines in slices 4–5, which still read it. |
| 3. Session tool loop | Done | Tool sessions without an execution environment (`run_tool_session` in `openai_hosted.py`): every pending call is answered exactly once, including after a dropped stream or a worker restart. A lost creation is found again by its metadata, and a failed turn reports the provider's code (`test_tool_sessions.py`, against a protocol-faithful fake). Every call is validated against its contract and logged once per session and call ID (`test_tools.py`, migration `0024`). Lanes (`lanes.py`, migration `0025`): threads sharing a four-connection pool, fenced writes, one heartbeat, LISTEN wake-ups, handoff on exit, retries, and a closer that records late usage and deletes sessions (`test_lanes.py`). They run inside the existing worker; its drain acknowledges a wake-up only when no item is runnable, and the recovery sweep counts run items (`test_worker_recovery.py`). Live with `gpt-6-luna`, one bill-shaped item ran through real lanes in about 20 s; the protocol facts are in the [evidence](evidence.md#the-tool-loop-measured-live-21-october-2026). 723 Python tests pass. |
| 4. Statement slice | Done | Statement entry 1.0 runs on the run model (`accounts/statement_entry.py`). Layouts are proved by balances and printed controls, with one layout session per unseen format and a date-order question that parks the sheet (`statement_layouts.py`). Chunks of up to 100 rows are routed through the desk lookups (`desk_tools.py`), and `propose` checks every row with `validated_plan`. Transfers are paired into one Contra, repeats in overlapping statements are written once, and a gap between statements raises one item (migration `0028`). Approved rows are durable `native_writes`, one `tally.write` at a time per PC, never re-sent after an interrupted save (`writes.py`, migrations `0026`–`0027`). The staged pipeline is deleted (`test_statement_entry.py`). Live, the PR Infra UAT scenarios S01–S06 behaved as specified, and a two-bank rehearsal saved and verified 10 vouchers in Tally ([evidence](evidence.md#statement-entry-rehearsed-live-21-october-2026)). 706 Python tests pass. |
| 5. Bill slice | Done | Bill entry 1.0 runs on the run model (`accounts/bill_entry.py`). One tool session per file reads every page as an image and, where the PDF has one, its text layer (`minkops_connectors/documents.py`). It routes each bill to the company it is addressed to, by any of that company's GSTINs, and proposes the client's own voucher. `propose` checks each bill at once with `vouchers.check`, whose printed taxable and tax totals expose tax-inclusive amounts. A total or round-off must be one the text layer prints. Confirmation by use: a booking unlike the supplier's history (another voucher type or ledger, or without the stock items it carried) waits for review even under standing approval, and one approval confirms it. A legible handwritten note is followed and quoted, and an unclear one holds. A bill repeated across files is written once, and differing versions all hold. Approved bills are native writes reconciled by document identity. A new supplier is created only on a person's decision and verified by readback (`tally.supplier`, migration `0029`). Source Discovery, the hosted-environment runtime and the staged bill pipeline are deleted (`test_bill_entry.py`, `test_bill_vouchers.py`). Live, the PR Infra UAT bills behaved as specified on a company that already held B01–B03, and the 15-bill synthetic package scored 15 of 15, its 8 saves verified in 27 s. Create this ledger created and verified a supplier ([evidence](evidence.md#bill-entry-rehearsed-live-21-october-2026)). 406 Python tests pass, fewer than slice 4's because the staged pipeline's tests went with it. |
| 6. Memory, rules and questions | Done | Employee memory per client business (`accounts/memory.py`). Verified saves a person approved become bookings (a supplier's voucher type and expense ledgers) and routings (a payee's counter ledger), one entry per treatment. One approval confirms a booking, so standing approval writes the next bill booked the same way. Every sync revalidates entries: an edit made in Tally demotes one, and one whose ledgers are missing from three syncs retires. Rules are people's own, versioned and cited by ID; sessions read every active rule, at most 30 per client and employee. Practice cards are answered through Attention's receipted decision path, and the bills that waited on them are released. Plans follow settled practice: receipt-register numbers in the narration, and the invoice number fields to search for duplicates. Sessions look up `memory`, `rules` and `practice`. An admin page and API edit memory (`test_memory.py`, `test_practice.py`, `test_memory_api.py`, `memory.spec.js`). PR Infra's installation creates its client business, seeds its agreed NEFT-return rule and adds its client procedure to both workflows. Live, a rule was cited, a practice answered, bookings and routings learnt, and an edit made in Tally demoted a booking; the next reading followed the corrected books ([evidence](evidence.md#memory-and-practice-rehearsed-live-21-october-2026)). 414 Python tests pass. |
| 7. Bill-wise link | Done | Plan protocol 6 carries bill references on any line, and the companion reads them back (`voucher.js`; companion 0.10.0 is now the minimum). A bill to a supplier that keeps bill-by-bill balances opens a New Ref under its invoice number; its credit note holds, because it must name the bill it adjusts. `mirror.open_bills` balances each bill from its origin: a New Ref, an Advance, or a ledger's opening bill when the books begin inside the mirror's window. Cancelled and optional vouchers settle nothing. A statement row to such a ledger settles its open bills (`accounts/settlement.py`): the bills the narration names, the only open bills that add up to the amount, or on account when nothing is open. A run's rows claim what they settle, so no balance is settled twice. Any other allocation holds as `bill_unresolved`, with one Settle button per allocation (`test_settlement.py`, `test_mirror.py`, `test_statement_entry.py`). A tool call that fails now rolls back its writes. Live on Third Tally Company, opening and New Ref bills balanced as Tally does. Four payments settled them by name, by amount and by one click, and a bill Minkops entered was settled by a payment Minkops entered, every reference verified in Tally ([evidence](evidence.md#bill-wise-settlement-rehearsed-live-21-october-2026)). 436 Python tests pass. |
| 8. Inventory | Done | A bill the client books item-wise carries its items (`vouchers.check`). Each is a stock item in its own unit, and quantity times rate reaches the printed amount. Its purchase ledger, which must affect inventory, carries its value, and its godowns take it whole. Tally books each purchase ledger's items as one line, so the plan does, and protocol 6's readback compares every item, godown, quantity, rate and amount. Batch-tracked items hold for entry in Tally. So do item-wise purchases where Receipt Notes or purchase orders track goods; a new `purchase_orders` probe settles the latter. Sessions look up `find_stock_item` and `godowns`, and bookings are learnt and compared item-wise or not. Each mirror version records the probes run on it, so a probe added later meets unchanged books, and a practice the books settle releases the bills waiting on it (`test_bill_vouchers.py`, `test_bill_entry.py`, `test_sync.py`, `voucher-write.test.js`). Live, an item-wise purchase of three items to two godowns was saved and verified in 3 s ([evidence](evidence.md#item-wise-purchases-rehearsed-live-22-october-2026)). 443 Python tests pass. |
| 9. E-invoice QR | Not started | |
| 10. Review surface | Not started | |
| 11. Hosted Tally | Not started | |
| 12. Performance | Not started | |
| 13. Cut-over | Not started | |

**Carried into later slices:**

- **Slice 10:**
  - per-client checks on reading or acting on one task or Attention item (the lists already filter by client);
  - the console design kit (`design/ui_kits/console`, `design/accounts.css`), which still shows the staged discovery screens.
- **Slice 12:**
  - usage for every attempt. A retry or a recheck replaces the previous attempt's usage today, so spend is under-counted;
  - shorter company handles in tools. Sessions mistype the 36-character company GUID about once per tool, and each mistype costs a round trip.

**For the next manual testing phase** (steps that need a person at Tally or Windows):

- **A first pass of the UAT bills.** The PR Infra UAT company already holds B01–B03 and B03's supplier from the staged build.
  1. Restore the pre-UAT backup the pack records, or a copy of the company without them.
  2. Run B01–B03.
  3. Expect B01 and B02 saved, and B03 held as Missing supplier with Create this ledger. After that decision, expect one new supplier with its statutory fields, and one purchase.

- **Split Company Data.**
  1. Split a copy of a rehearsal company in Tally's UI.
  2. Open both halves and request a sync.
  3. Expect the sibling with the new BooksFrom to raise its own "New company found" card, and the original to keep its mirror.
- **Interrupt a save.**
  1. Approve a statement row, and close the companion while it writes.
  2. Reopen the companion.
  3. Expect the row to hold as Save interrupted. Retry save then either finds the voucher in Tally (saved) or holds it
     as an uncertain import; it never imports twice.
- **Restore an older backup.**
  1. Back up a rehearsal company, add a voucher and sync.
  2. Restore the backup in Tally's UI and sync again.
  3. Expect a full rebuild with reason `marker_regressed`, and the added voucher gone from the new version.
- **Bills in Tally's own reports.** The slice 7 rehearsal checked bill references through Tally's XML export only.
  1. In Third Tally Company, open Display More Reports > Statements of Accounts > Outstandings > Ledger for QA18 Billwise Steel.
  2. Expect only QA18/OB/001 pending, with 3,000.00 open. QA18/BW/101, QA18/BW/102 and QA18/BW/103 should be cleared by
     the payments Minkops entered.
