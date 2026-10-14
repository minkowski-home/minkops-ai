# Plan: Tally field reliability (companion 0.7.0)

Status: final draft, 14 Oct 2026. Deadline: the next PR Infra meeting, within a
week. Source: the failed Source Discovery demo on PR Infra's PC `Prahlad-Gadhwal`
(companies *Sachin Infra (…)*). When implemented, fold the contracts into
[source discovery](source-discovery.md), [Windows app](windows-app.md) and
[attention](attention.md), record the decision in [decisions log](decisions-log.md)
(it supersedes the "Company on Disk" entry), and delete this file.

PR Infra is the first field case, not the target. Every fix below is a generic
capability of the core workflows. Client practices that vary are handled by
existing per-run choices or defaults in the client's composition under
`solutions/<client>/`, never by code paths or data models shaped around one client.
Until the PR Infra demo succeeds, `mock-client` stands in for PR Infra (section 6).

## 1. Field evidence

### Environment observed on the PC

| Fact | Value | Generic lesson |
| --- | --- | --- |
| Edition | TallyPrime **Edit Log**, local desktop icon | Editions vary; never gate on edition |
| Executable | `D:\TALLY PRIME\tally.exe` | Install locations vary; never locate Tally |
| `tally.ini` | `Data=D:\TALLY PRIME\SACHIN INFRA ORIGINAL DATA`, `Load=100000`, `ServerPort=9000` | `Data=` names one folder; practices use several |
| Companies | Password-protected, spread across several folders on `D:` | Credentials and folders belong to the user's Tally session |
| Company numbers | Folder-local: every folder numbers from `100000` | Numbers are not identities |
| Unopenable company | Sachin Infra (2017-18): `Migration Required` | Some companies on disk can never load |
| Year structure | One company per financial year (2023-24 … 2026-27) | A practice choice; the user picks the company per run |
| Connected PC | First probe ran on the user's Remote Desktop session, not this PC | The PC running Tally must be explicit |

### Production timeline (UTC, 14 Oct; `desktop_jobs`, `discovery_runs`, `task_events`)

| Time | Job | Outcome |
| --- | --- | --- |
| 06:57 | `tally.probe` on `Prahlad` | Failed: wrong machine (Remote Desktop session; device later revoked) |
| 07:05:07 | `tally.probe` | Succeeded: `Sachin Infra (2026-27)` |
| 07:05:33 | discover `d969e02d` | "Tally needs attention… close Tally" (19 s) |
| 07:06:28 | discover `2ce62ea3` | "Tally installation was not found" (6 s) |
| 07:17:00 | discover `853f8447` | "Tally company scope could not be verified" (9 s) |
| 07:32–07:45 | discover ×4 | Alternating "Close Tally" / "Not installed" |
| 07:46, 07:47 | `tally.probe` ×2 | "Tally is not responding"; diagnostics show `fetch failed`, `process_disappeared: true`: Tally had been quit |

API, worker, scheduler and database behaved correctly throughout.

## 2. Root causes

| # | Cause | Code |
| --- | --- | --- |
| RC1 | Discovery requires every company in the `Data=` folder to be open and restarts Tally to load them. Passwords, unmigrated companies and other folders make that impossible. | `ensureTallyDiscovery`, `tally-recovery.js:106-194`; `client-context.js:70-112` |
| RC2 | Closing Tally waits 10 s; a human answering Quit takes longer, so success is reported as failure. | `CLOSE`, `tally-recovery.js:397-403` |
| RC3 | A closed Tally is searched only in App Paths and `Program Files`, so it is reported "not installed". | `INSTALLATION`, `tally-recovery.js:378-395` |
| RC4 | Identity uses the folder-local `CompanyNumber`: open companies from two folders collide ("scope could not be verified"), and merging with `Company on Disk` raises "conflicting identities". | `tally-recovery.js:85-90`; `client-context.js:85-102` |
| RC5 | Every read error (timeout, refused, parse, conflict) becomes one message, and the worker overwrites connector errors with "Tally is not responding". | `tally-recovery.js:92-94`; `platform/desktop-runtime/src/worker.js:37-45` |
| RC6 | Check connection reads open companies; discovery demanded all on disk. They disagreed. | `tallyProbe` vs `ensureTallyDiscovery` |
| RC7 | Diagnostics keep only `fetch failed`, stay on the PC, and need PowerShell to retrieve. | `main.js` `diagnose` |
| RC8 | The companion cannot auto-update, and the server cannot tell which version a PC runs. | `apps/windows-app/package.json`; `desktop_devices` |
| RC9 | Progress text is mis-encoded (`sourceâ€¦`). | `platform/src/minkops_platform/discovery.py:364` |

## 3. Principles

1. **Tally is the user's application.** Minkops never starts, closes, restarts or
   locates Tally, never handles its passwords, and never chooses its data folders.
   It works with the companies the user has open, from any folder.
2. **One environment check, everywhere.** Check connection, the discovery
   preflight and the pre-save check share one read-only classifier, so they can
   never disagree.
3. **Every field problem is a typed state** with one user action, a short label
   naming the PC and company, and an internal diagnostic. No catch-all messages.
4. **Core is generic; no client-shaped models.** Prefer an existing per-run
   choice or a composition default over a new option. Read client facts (voucher
   types, ledgers, companies) from Source Discovery instead of hard-coding them.

## 4. Layer responsibilities

| Layer | Owns in this plan |
| --- | --- |
| `connectors/desktop` | Tally session reads (open companies, periods), the error classifier, the request transport (write detection, ambiguity marking). No process control. |
| `platform/desktop-runtime` | Passing typed connector errors through job receipts; attaching bounded diagnostics to failed Tally jobs. |
| `apps/windows-app` | Wiring, the *Send diagnostics* tray action, version header, auto-update. |
| `platform/src/minkops_platform` | Discovery scope comparison, Bill Entry purchase voucher type selection and holds, diagnostics storage, version gating. |
| `apps/solution-api`, `apps/solution-web` | Endpoints and screens: review scope changes, PC version and name, update prompt. |
| `employees/accounts-desk/workflows/*` | Core contracts and instructions; no new tenant options in this plan. |
| `solutions/mock-client/employees/accounts-desk/` | Stand-in for PR Infra until the demo succeeds: Bill Entry defaults `company_mode: locked`, `review_mode: all_outputs`. No code. |

## 5. Core contracts

### 5.1 Tally session

- **Scope = companies open in Tally.** Read only the `Company` collection with
  `Name, GUID, CompanyNumber, StartingFrom, BooksFrom`. `Company on Disk` is no
  longer read; it covers one folder and misleads in multi-folder practices.
- **Identity = GUID.** Name and number are display data. Duplicate GUIDs or names
  among open companies (e.g. an original and a copied folder both open) block with
  "Two open companies are named *X*. Close one in Tally, then retry", because
  requests address companies by name (`SVCURRENTCOMPANY`).
- **Cap** of 50 applies to open companies.
- **No lifecycle code.** Delete `closeTallyProcess`, `restartTallyProcess`,
  `waitForTally`, `inspectTallyInstallation`, `startupCompanies`,
  `captureTallyProcess`, the `CLOSE`/`INSTALLATION`/`PROCESS` scripts and their
  exports; the companion drops `state.tally_startup` and
  `state.tally_company_numbers` on load. A single read-only "Tally processes
  running" check remains for classification and diagnostics.
- **Transport.** `recoveringTallyRequest` becomes `tallyTransport`: keeps write
  detection and ambiguity marking; never restarts. Reads that time out are retried
  at most twice with backoff (a user may briefly have a dialog open); writes are
  never retried.

### 5.2 Environment check (`checkTally`)

Decided from `error.cause.code`, timing and the read-only process check. Every
message names the PC.

| State | Detection | Message |
| --- | --- | --- |
| `not_running` | Refused, no Tally process | "Tally isn't open on *PC*. Open it and your companies, then check again." |
| `port_closed` | Refused, Tally process running | "Tally on *PC* isn't accepting connections on port *N*. In Tally: F1 → Settings → Connectivity." |
| `busy` | Timeout after retries | "Tally on *PC* is waiting on a screen. Finish any password prompt or open dialog, then check again." |
| `no_company` | Valid response, no companies | "Open at least one company in Tally on *PC*." |
| `duplicate_company` | Repeated name or GUID | "Two open companies are named *X*. Close one in Tally." |
| `multiple_instances` | >1 Tally process (warning, not a block) | "More than one Tally is open on *PC*; Minkops uses the one on port *N*." |
| `invalid_response` | Unparseable or failure status | "Tally on *PC* returned an unexpected response." + diagnostic |
| `ready` | | Lists open companies with their periods |

`tally.probe` (Check connection), the discovery preflight and the Bill Entry
pre-save check all call `checkTally`. Connector errors carry `{state, userMessage}`;
`worker.js` passes `userMessage` through and keeps its generic fallback only for
untyped errors.

### 5.3 Source Discovery

- Collect every open company. Tally closing mid-run fails the run as
  `not_running` with "Reopen Tally and your companies, then run discovery again";
  nothing is replayed.
- **Scope changes are shown at review.** The server compares the package's GUIDs
  with the tenant's last confirmed discovery: "No longer included: *X*" and
  "Newly included: *Y*". Confirming accepts the new scope. No attention item.
- Review heading: "Discovered from the *N* companies open in Tally on *PC*".
- Plan v3 (`X-Minkops-Plan-Version`) carries the open-scope contract; older
  companions are not dispatched discovery (5.5).

### 5.4 Bill Entry

- **Company per run.** The existing "Use one company for this run" choice
  (`company_mode: locked`) covers practices with one company per financial year:
  the user picks the company the batch belongs to and keeps it open. The client's
  composition defaults to it, and the launch never silently preselects a company
  when several were discovered. "Infer from each bill" stays available. The
  existing `date_before_books` hold stops bills dated before the chosen company's
  books. Residual risk: Tally accepts *later* dates in an older year's company;
  the operator selects `all_outputs` for first live runs (the default stays
  `only_exceptions`) and sees the date in the details card (5.4.1).
- **Pre-save check** (companion, before every import): `checkTally`, then the
  destination GUID must be open. Not open: hold with attention "Open *X* in Tally
  on *PC*" and **Retry save** / **Do nothing**; other bills continue.
- **Unknown write outcomes** stay reconciliation-only receipts, never replayed.
  If Tally is closed, the bill holds until it is open and reconciliation runs.
- **Native rejections** are classified into short labels (date, permission,
  voucher type, ledger, voucher number, other); the native `LINEERROR` goes to
  the job's diagnostic, not the label.

#### 5.4.0 Purchase voucher types (from discovery, never hard-coded)

Today Bill Entry requires a type named `Purchase` (`bills.py:224-228`), checks
duplicates only among `Purchase` vouchers (`tally.js:133`) and always writes
`VCHTYPE="Purchase"` (`tally.js:308`). Clients that book purchases under their own
types (e.g. *Purchase GST*, *Purchase - Local*) would get duplicates missed and
bills filed under the wrong type.

- **Base type.** A voucher type's base is its `RESERVEDNAME` when Tally marks it
  predefined; otherwise follow `PARENT` by name (case-insensitive, cycle-guarded)
  until a predefined or self-parented type. The *purchase family* is every type
  whose base is `Purchase`, active or not. One rule, implemented and tested
  identically on the server (selection) and the companion (live checks).
- **Selection per company, per run.** Candidates are the family's *active* types
  (`ISACTIVE` not `No`). One candidate: used automatically. Several: the launch
  screen asks, preselecting the type most used in the discovered vouchers (no
  preselection on a tie). None: that company cannot take bills, with a clear
  message. Choices travel as `purchase_voucher_types: {company GUID: type GUID}`;
  in "infer" mode an unresolved company holds only its own bills.
- **Pinned and rechecked.** The chosen type (name, GUID, parent, AlterID) is pinned
  in the run target and in each write plan (plan format 3; older companions
  cannot receive it). Before writing, the companion rereads voucher types and
  requires exactly one live type of that name with the same GUID, still in the
  purchase family and active; otherwise the bill holds with "The purchase voucher
  type *X* changed since discovery. Refresh Source Discovery, then start a new
  run."
- **Duplicates across the family.** Duplicate, correction and reconciliation
  reads cover every purchase-family type, including inactive ones and types
  created after discovery. A *Journal*-based voucher with the same supplier,
  invoice number and financial year holds as "Already recorded as a Journal
  voucher" and is never altered.
- **Corrections keep the existing type**; new vouchers use the pinned type; the
  readback must show the expected type.

#### 5.4.1 Review details card

Each proposal in the run review gets **Show details**: a small card showing
exactly what will be entered in Tally: company, voucher type, date, supplier
ledger, invoice number, purchase ledger and amount, each tax ledger and amount,
total, and whether it creates a voucher or corrects an existing one. Actions stay
**Write bill** / **Do nothing**.

### 5.5 Companion identity, version and auto-update

- Every worker request sends `X-Minkops-Companion-Version`; `desktop_devices`
  stores `companion_version`, `hostname` and `remote_session` (Windows
  `SESSIONNAME` starts with `RDP-`) on each claim (migration).
- Console shows each PC as *name (hostname), version*, and warns "This PC is a
  Remote Desktop session" when the user connects one. Tally jobs for companions
  older than 0.7.0 are not dispatched; the console says "Update Minkops on *PC*".
- **Auto-update** with `electron-updater`: generic feed on the existing Firebase
  Hosting next to the installer, blockmap differential downloads (installer
  ~103 MB). Downloads in the background; installs on quit or when idle, never
  while a job is claimed or a receipt is pending. SHA-512 verified; code signing
  is scheduled separately to remove SmartScreen friction. 0.7.0 is the last manual
  install, so any later fix in this plan can ship as 0.7.x.

### 5.6 Diagnostics

- **Automatic:** a failed Tally job's receipt carries a bounded diagnostic
  (≤16 KB): typed state, `cause.code`, elapsed time, process check, open companies
  (name, GUID, period), native `LINEERROR`.
- **Send diagnostics** (tray menu): companion and Windows versions, hostname,
  session type, Tally process count and product version, port reachability,
  open companies, whitelisted `tally.ini` keys (`ServerPort`, `Data`,
  `Client Server`), the last 20 job outcomes and local diagnostic records. Shows a
  short reference (e.g. `D-7K2Q`) for the user to read out.
- Never included: bill contents, XML bodies, file contents, credentials.
- Stored in `desktop_diagnostics` (tenant, device, job, kind, payload ≤64 KB),
  30-day retention via `infra/configure_retention.py`, operator access by SQL. A
  console viewer is later work.

### 5.7 Field gotcha register

Each problem found on 14 Oct and its generic handling. Rehearsal (section 8)
exercises every row.

| Gotcha | Generic handling |
| --- | --- |
| Tally installed outside `Program Files` | Never located (5.1) |
| Passwords on companies | User opens them in Tally; `busy` while a prompt waits (5.2) |
| Companies in several folders | Open-company scope, no `Data=` reliance (5.1) |
| Same company numbers across folders | GUID identity (5.1) |
| Copied company open alongside the original | `duplicate_company` block (5.2) |
| Unmigrated companies on disk | Never touched; not part of scope (5.1) |
| Partial scope triggering a restart | No lifecycle code (5.1) |
| Quit confirmation slower than a timeout | Minkops never quits Tally (5.1) |
| Check connection disagreeing with discovery | One `checkTally` (5.2) |
| "Not responding" for every error | Typed states, pass-through (5.2) |
| Wrong PC / Remote Desktop session | Hostname and session shown and warned (5.5) |
| One company per financial year | Company chosen per run, `date_before_books` hold (5.4) |
| Custom purchase voucher types | Selected from discovered voucher types (5.4) |
| Company closed between discovery and save | Pre-save check, Refresh (5.4) |
| Tally closed mid-run or mid-write | Typed failure; reconciliation-only writes (5.3, 5.4) |
| Restricted Tally user role | Classified `permission` rejection (5.4) |
| Old companion on the PC | Version gating and auto-update (5.5) |
| No remote evidence | Automatic and on-demand diagnostics (5.6) |
| Mis-encoded progress text | RC9 fix |

## 6. Client composition (mock-client stands in for PR Infra)

Until the PR Infra demo succeeds, all work and the meeting run use the
`mock-client` composition. Its Bill Entry binding defaults change to
`company_mode: locked`; `review_mode` stays `only_exceptions` and the operator
selects `all_outputs` per run.

At PR Infra installation, transfer only the client choices into
`solutions/pr-infra/employees/accounts-desk/` (binding defaults and a short
`client-instructions.md`), and install through the validated CLI. Do **not**
carry over mock-client's fixture instructions (synthetic RC suppliers, *Test
Company* mappings, the billing-Ref convention); they are demo-only.

Confirm with the client before the meeting:
- Which data folder holds the live books, and whether copies exist elsewhere.
- That the Tally user who enters bills can create vouchers and ledgers.

## 7. Tests (write first)

Connector (`node --test`):
- One open company: collected; no `Company on Disk` request; no process control
  exported from the module.
- Two open companies from different folders, both `100000`: both collected by GUID.
- Duplicate name open: `duplicate_company`, nothing collected.
- Classifier: refused + no process → `not_running`; refused + process →
  `port_closed`; timeout after two retries → `busy`; empty → `no_company`.
- Tally disappears mid-collection: `not_running`, no replay.
- Write fails with Tally gone: reconciliation-only receipt, never replayed.
- Probe, discovery and pre-save return the same state for the same session.

Connector: duplicate checks and reconciliation see vouchers of every pinned
purchase-base type; the import writes the pinned type.

Runtime and companion: typed `userMessage` passes through `worker.js`; untyped
errors keep the fallback; failed Tally receipts carry a diagnostic within its size
bound; updater never installs with a claimed job or pending receipt.

Server (`pytest`): plan v3 gating; version, hostname and session recording;
dispatch refused below 0.7.0; review scope changes against the last confirmed
discovery; purchase voucher type selection (only `Purchase`; one custom type;
several types with the most-used default; inactive types ignored; none → clear
hold); destination-not-open hold and Refresh; diagnostics endpoint size and tenant
isolation; encoding regression.

## 8. Rehearsal (Windows VM, before release)

A generic matrix, not a copy of one PC: TallyPrime installed under `D:\`; two data
folders whose companies share numbers; one unmigrated company; passwords on all
companies; one restricted-role user; companies split per financial year; one
company using a custom purchase voucher type; Quit confirmation enabled.

Run Check connection, discovery and Bill Entry with: one company open; three open
across folders; a password prompt left on screen; an original and a copy both
open; Tally closed; Tally closed mid-discovery and mid-save; a run locked to the
2026-27 company with bills dated 31 Mar and 1 Apr; a duplicate of a voucher saved
under the custom type; the restricted user saving a bill; companion 0.6.10 updating
to 0.7.0 then to a test 0.7.1. Each run must show the expected typed state and
produce a retrievable diagnostic.

## 9. Delivery

Branch `platform-desktop/tally-open-company-scope`, merged to `staging`.

Must be in companion 0.7.0 (client reinstall):
1. RC9 encoding fix (server only, ships at once).
2. `checkTally` classifier, typed pass-through, Check connection on it.
3. Open-company scope, GUID identity, delete the Tally lifecycle code.
4. Purchase voucher types from discovery (server selection, companion checks).
5. Bill Entry pre-save check and rejection classification.
6. Diagnostics: receipt attachment, *Send diagnostics*, `desktop_diagnostics`.
7. Version, hostname and session header; console gating and PC labels.
8. Auto-update.

Server-side, may land just after 0.7.0 without a reinstall:

9. Discovery review scope changes.
10. Review details card; mock-client defaults (`locked`).
11. Docs and decisions-log STAR entry; delete this plan.

If the week runs short, item 9 moves after the meeting.

## 10. Meeting runbook

1. Install Minkops 0.7.0 over 0.6.10 (sign-in is kept; last manual install).
2. On the PC itself (not Remote Desktop), open TallyPrime and the companies to work
   with, finishing every password prompt. Other folders: Select Company → change
   path.
3. Check connection: expect *ready* listing exactly those companies, labelled with
   this PC's name.
4. Run Source Discovery once with Tally open and idle; expect *completed*, review
   the listed companies, confirm.
5. Bill Entry: choose the company for this run (keep it open in Tally), then 2–3
   bills dated inside its year, in review mode.
6. If anything fails: tray → *Send diagnostics*, note the reference.
7. Operator check: `discovery_runs.state = 'completed'`, `catalog.partial = false`,
   `desktop_devices.companion_version = '0.7.0'`.
