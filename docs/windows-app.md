# Windows app and companion (MIN-117)

The Windows 10/11 x64 app loads the same deployed React application as the web
app, reusing verified email/password accounts, memberships, workflows, reviews
and task history. The native host adds folder selection and a tray companion;
one workspace/account is connected per running installation.

This revision builds companion 0.11.0 (plan protocol 6; see its contracts below);
the last release recorded in `windows-release.json` is 0.9.1. The server refuses
Tally work from companions older than 0.11.0. The companion works only with the companies open
in the user's own Tally, reports typed session states, sends diagnostics and
updates itself. For Tally on a hosted server, see [Hosted Tally](hosted-tally.md). Its Tally sync uses HTTP/XML exports and needs no
ODBC driver. Windows 10 device testing was deferred by the owner; compatibility
is retained.

## Local capabilities

| Operation | Desktop | Web with a connected PC | Authority |
| --- | --- | --- | --- |
| Check Tally | Yes | Yes | Fixed, read-only company export from this PC's Tally port on `127.0.0.1` (9000 unless set under Connected PCs) |
| Sync Tally books | Yes | Yes | Read-only: each authorised company's masters and vouchers into the server's mirror, in bounded pages |
| Connect a folder | Native picker | Open desktop to grant it | Explicit local selection; snapshots must match the uploaded source |
| Refresh a connected folder | Yes | Yes | Owned device/source binding; limited supported files |
| Save approved Tally vouchers | Yes | Yes | Pinned company and ledger references, the immutable approved plan, durable intent before import and exact readback |
| Create an approved supplier | Yes | Yes | One GST creditor a person approved, modelled on a same-company creditor and verified by readback |

This version adds bounded native operations, not customer-machine agent hosting
or a general remote shell. See [Bill entry](bill-entry.md) and
[Statement entry](statement-entry.md). Open Tally with its HTTP server enabled on
port 9000, with every company a run may use loaded, so the sync sees them. A
company listing is a connection check, not verification of financial writes.

Close hides the app in its tray; **Quit Minkops** stops the companion. Queued
manual work runs while the companion is connected, including requests from the
web. There is no scheduler, missed-run handling, startup-at-login policy or
Windows service. Scheduling is [MIN-121](https://linear.app/minkops/issue/MIN-121).

## Data and recovery

PostgreSQL remains authoritative for accounts, access, selected file versions,
approvals, task observations and receipts. The warehouse is still reserved for
a separate pipeline. No local mirror of task history is added.

The PC necessarily holds Chromium's signed-in session/cache, an installation
ID, one scoped device credential, granted folder bindings, an unfinished receipt
and recovery backups. Native state and backups use Electron `safeStorage`
(Windows DPAPI, via [Electron safeStorage](https://www.electronjs.org/docs/latest/api/safe-storage)); encryption failure prevents persistence. Credentials never
enter the renderer, and absolute folder paths stay on the PC. Backups are deleted
after successful server acceptance; interrupted/unverified backups remain
encrypted for recovery. State is under Electron's per-user Minkops app-data
directory. Original business files remain in the selected folder.

Device credentials are hashed on the server, rotate on reconnect, expire after
90 days and stop working on revocation or lost membership. Desktop logout stops
its companion; web users can revoke a PC in Connected PCs. An operation already
saving cannot be rolled back by logout or cancellation. Late domain receipts
record what was actually applied without marking a cancelled run complete.

Only read jobs are automatically reclaimed after the two-minute lease. Saves
are not automatically dispatched twice on lease expiry: an interrupted save holds
until Retry save reconciles it with Tally. A persisted receipt is retried before
further work. Domain side effects and job state commit atomically.

The companion polls outbound HTTPS every four seconds. It opens no inbound
server and needs no browser loopback exception, firewall port or router
forwarding. Future mobile clients can use the same server-owned tasks and
request bounded work on an authorized connected PC.

Presence is independent of job dispatch: authenticated companion traffic updates
`last_seen_at`, and busy workers send a bounded, single-flight heartbeat without
claiming another job or extending its lease. Completion uploads have a two-minute
client budget; control requests retain
45 seconds, and failed deliveries retain their durable receipt. Release the API
heartbeat endpoint before rolling out a companion that calls it.

## Tally session, diagnostics and uncertain writes

Tally belongs to the user. The companion never starts, closes, restarts or locates
Tally, never handles company passwords and never chooses data folders; it works
with the companies the user opened, from any folder (`connectors/desktop/src/tally-session.js`).
Check connection, the sync and the check before every save share one read-only
classifier, so they cannot disagree. It reads the open
`Company` collection and, on failure, the error cause plus a read-only process
check, and returns one typed state whose message names the PC:

| State | Meaning |
| --- | --- |
| `not_running` | No Tally process, or none reachable |
| `port_closed` | Tally runs but refuses connections on the port (Help > Settings > Connectivity) |
| `busy` | Timed out after two retries: a pending prompt or a very large report |
| `no_company` / `duplicate_company` / `too_many` | Open-company scope is empty, ambiguous by name, or over 50 |
| `company_not_open` | A save's company is not open, or a same-named copy is open instead |
| `invalid_response` | Unparseable or failed reply |
| `other_session` | The Tally on this PC's port runs in another Windows user's session, as on a shared server |
| `ownership_unknown` | On a remote session, the session serving the port could not be observed |

Before the check reads anything, one read-only PowerShell observation names the
process listening on the port, its Windows session, the companion's own session
and the running Tally processes. A Tally in another session is never read or
written. Where nothing can be observed, a console session proceeds as before and a
remote session refuses. Each PC's port is set under Connected PCs; every job and
heartbeat carries it, so the check and diagnostics read the same Tally as syncs
and saves.

Typed messages pass through job receipts verbatim; untyped errors keep a generic
fallback. Before each save the company must be open and match the synced GUID;
session problems and native rejections (classified as date, permission, voucher
type, voucher number or ledger) become holds with a specific attention label that
**Retry save** clears once Tally is ready.

Reads that time out may repeat twice. Imports never repeat: after a lost
acknowledgement or failure response, a fresh read-only reconciliation checks
whether the exact approved bill exists. Matching data produces a duplicate receipt,
a different version is held, and a missing bill requires review and Retry save.
If Tally closed, the bill holds until it is open again. External writers can race
read/import; Tally offers no transaction spanning those separate requests, so
ambiguity remains a handoff.

Bill saves use the voucher type the approved plan names, one of the mirrored types
whose predefined base is Purchase (`RESERVEDNAME`, else the `PARENT` chain).
Duplicate, correction and attention reads cover every purchase-based type,
including inactive ones, and a matching Journal voucher holds instead of being
repeated. Before writing, the live type must still exist with the same GUID, be
purchase-based and active. Corrections keep the existing voucher's type.

Each failed or retried Tally job attaches a bounded diagnostic (state, cause code,
elapsed time, recent Windows crash events) to its receipt, and the local
`tally-diagnostics/<job-id>.json` record remains. **Send diagnostics** (tray menu or
the PCs screen) posts a summary of versions, PC name, Remote Desktop session, Tally
processes, the session check, whitelisted `tally.ini` settings and recent job
outcomes, and returns a reference such as `D-7K2Q4M`; offline, it copies the
summary instead. The server keeps diagnostics for 30 days in `desktop_diagnostics`.
Bill data, request XML, file contents and credentials never leave the PC.

Every poll reports the companion version, hostname and whether the session is a
remote one (any session but the console). The console shows them with the PC's
Tally port, and the server refuses Tally work from companions older than 0.11.0
with "Update Minkops on *PC*", and hands an older one none already queued. A PC
that has not polled yet may queue work.

`node scripts/verify_tally_session_live.mjs [port] [company] [guid]` prints the
typed state on a Windows PC without changing Tally, for rehearsals.

## Build and run

Run `db/migrate.py` before starting a new revision; it installs the baseline on a
fresh database and applies every later migration in order (see
[database migrations](../db/README.md)). See [workflow authoring](workflow-authoring.md)
for installation and recovery.

Use Node 24 and the existing Python/uv workspace. From the repository root:

```sh
cd connectors/desktop && npm ci
cd ../../apps/windows-app && npm ci
npm test
npm run build
npm run package:win            # a release, signed by its publisher
npm run package:win:candidate  # an unsigned release candidate
```

Build on Windows with a Windows-local checkout and Node/npm. WSL symlinks are
unsuitable for Windows packaging tools. `bundle/` contains compiled runtime,
connectors, assets and minimal application metadata. Electron is external;
development dependencies are not shipped. Native dependency rebuilding is
disabled because this bundle has no native Node modules; revise before adding
one. Electron's version is pinned in the manifest and lock.

`npm start` runs the developer app. Set `MINKOPS_APP_URL` to the app origin;
default is `https://app.minkops.com`. Packaged releases accept HTTPS only.
Development can use localhost HTTP. The web host must serve existing `/api/`
routes at the same origin; Vite already supports this through `VITE_API_TARGET`.
A build does not deploy or prove that the default production host serves this
branch. Run the migrations before using bill entry. Use normal
production email verification and secure session settings; never production
`AUTH_DEV_MODE` or demo seeding.

For a locally installed build, `Minkops.exe --local-demo` uses the fixed
`http://127.0.0.1:3018` origin and isolated `Minkops Local Demo` profile. The normal
packaged profile remains HTTPS-only. This switch grants no general URL override.
The local profile retains encrypted registration credentials and folder grants
across install/restart; keep the local API/UI/worker services running for testing.

Configure an edge request limit of at most 42 MB on the base64 folder receipt
route, with smaller limits elsewhere. Services/native adapters enforce 100
supported files, 5 MB per file, 30 MB per snapshot and folder containment.
A release is signed. `npm run package:win` needs the organization's code-signing
certificate (`WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD`) and
`MINKOPS_WINDOWS_PUBLISHER`, the certificate's common name, and refuses to build
without them (`scripts/package.js`). electron-builder signs the installer and pins
the signer in the update settings (`app-update.yml`), so an installed companion
accepts only updates signed by the same publisher. After the build, Windows must
trust the installer's signature, and both the signer and the pinned name must be
that publisher. `npm run package:win:candidate` builds an unsigned release
candidate on purpose, ignoring any certificate at hand; its updates do not check
their publisher. The packaged profile uses `https://app.minkops.com`.

The release manifest (`windows-release.json`) names the publisher of a signed
release, or says `"unsigned": true` for a candidate, whose release notes must
disclose it. Publication refuses a release whose installer's Authenticode
signature names anyone else, or no one (`infra/deploy_hosting.py`).

From 0.7.0, packaged companions update themselves from the generic feed at
`https://minkops.com/downloads/` (electron-updater). `npm run package:win` writes
`release/Minkops-Setup-<version>.exe`, its `.blockmap` and `latest.yml`. Update
`apps/corporate-website/frontend/src/content/windows-release.json`, then run
`infra/deploy_hosting.py corporate --installer release/Minkops-Setup-<version>.exe`;
it refuses a feed whose version, file name or SHA-512 differs from the reviewed
installer and publishes all three files together. Updates download in the
background (blockmap differential downloads) and install on quit, or once the
companion is idle: no claimed job, no unsent receipt and no focused window.
From 0.8.1 the console also shows update status and **Restart when safe**, which
waits for local work and receipts even while the window is focused. Frontend
releases have a separate explicit refresh banner. See [run limits and updates](run-limits-and-updates.md).
Downloads are SHA-512 verified; an unsigned release candidate still shows
SmartScreen on first install.

Run `npm ci` in this app before building a release. Its `.npmrc` packages the two
local modules rather than depending on Windows junction traversal, and this
app's lockfile pins their transitive dependencies. After editing either local
module, reinstall before building: packaged copies do not update automatically.

## Progress and review

Task detail leads with a short status, an observed stage and a business summary.
Runs use Get ready → Read → Review → Save → Finished; connection checks and folder
refreshes have their own short stages (Your PC → Check Tally or Read folder →
Finished). Events drive stages,
with no simulated percentage or ETA. Failures remain at the last observed
stage. Labels and outlined icons work independently of color or animation.

Review shows actual sheet/entry counts, bill identifiers and short status.
One-click decisions replace accounting editors and correction prompts. Manual
changes belong in the original tools; detailed events remain internal audit data.
All four themes and responsive layout are shared. Accounts alone decides when
every bill is verified; one native job cannot complete a multi-bill run.

## Verification

Tests use real PostgreSQL and sessions for ownership, tenant isolation, CSRF,
revocation, rotation, concurrent claims, request/receipt replay, invalid folder
snapshots, approval, read recovery and cancellation. Native tests cover fixed
Tally XML, limits, folder containment (Windows junctions and Linux symlinks),
already-saved recovery, receipt replay and IPC origin/frame isolation.

For an opt-in Windows-native HTTP smoke against a disposable localhost API with
`AUTH_DEV_MODE=1`, set `MINKOPS_SMOKE_URL=http://127.0.0.1:8117` and run
`npm run test:http`. It creates a dummy workspace and temporary files, refreshes
through HTTP/PostgreSQL, loses a server acknowledgement, recreates the worker,
replays the receipt, checks Tally availability and revokes the PC. It makes no
accounting writes or paid agent calls.

Set `MINKOPS_SMOKE_EXPECT_COMPANY` to an open test company's exact name to require
a successful live Tally export and verified server task completion. Typed XML
name elements are parsed as text; malformed nested names are rejected rather
than converted into misleading object strings.

Closing the main window leaves the native worker in the tray; a web-requested
sync or save finishes there, and reopening shows its result.

Native suites pass on Linux and Windows; Windows skips only a file-symlink test
that requires creation privileges (the same guard runs on Linux). A fresh
Windows 10/11 device matrix, a screen-reader audit, a release signed with the
organization's certificate and a shared server with two users have not been
verified.

### Companion 0.11.0 contracts

0.11.0 is the minimum for all Tally work. It confirms that the Tally on its port
is its own Windows user's ([Hosted Tally](hosted-tally.md)), and a protocol 6
bill may state its GST for Tally's returns:

- **GST.** A Purchase or Debit Note into a GST-registered company may carry
  `gst`: the supplier's GSTIN, registration type, state and country, the place
  of supply, the company's GSTIN, and, among several registrations, the one the
  bill is addressed to. A Purchase's taxed ledger lines may carry `gst`: their
  taxability, goods or services, and each duty head's rate. The companion writes
  them as Tally's party details and, on the line, rates "Specify in Voucher": an
  imported voucher without them is one Tally's returns list as uncertain (see
  [Bill entry](bill-entry.md#gst-returns)).
- **Readback.** Every voucher read back carries `gst`: the party details Tally
  stored, the company GSTIN it attached, and its own verdict for its returns
  (`included`, `uncertain`, `excluded`, `not_applicable` or `unknown`). None of
  it enters the voucher's fingerprint, because Tally restates its verdict when
  masters change.

### Companion 0.10.0 contracts

Plan protocol 6 is protocol 5 plus bill references and inventory:

- **Bill references.** A line may carry `bills`: New Ref, Agst Ref, Advance and
  On Account amounts that add up to the line's amount. Every type but On Account
  names its bill. A bill to a supplier that keeps bill-by-bill balances opens a
  New Ref under its invoice number, and a payment or receipt settles the party's
  open bills (see [Statement entry](statement-entry.md#bill-by-bill-parties)).
- **Inventory.** A Purchase may carry `inventory`: each stock item with its
  quantity in its own unit, rate, amount and godowns, and the purchase ledger
  line that carries its value. Each such line carries exactly its items' value.
  The companion writes the purchase in Tally's invoice view, each godown as a
  primary batch, after rechecking that the stock items keep their unit and no
  batches and that the godowns are the ones the run read (see
  [Bill entry](bill-entry.md#item-wise-purchases)).

The readback must carry exactly the approved references and items, signed as
Tally signs their line. A voucher with tracked batches, orders or receipt
notes, or with more than one purchase ledger per item, is more than a plan
states. The server sends a protocol 6 plan only to a companion that runs it,
0.10.0 or later; a protocol 5 plan approved before the upgrade stays
executable.

### Companion 0.9.0 contracts

Plan protocol 5 adds one native writer for every accounting voucher family:
Purchase, Journal, Debit Note, Payment, Receipt and Contra
(`connectors/desktop/src/voucher.js`). A v5 plan states a header and 2–40
balanced ledger lines, each with at most one cost centre/category allocation.
The companion rechecks the pinned company, ledgers (GUID, parent, AlterID),
voucher type (GUID, active, family) and allocation masters, then reads only the
plan's date window before deciding:

- `document` plans (bills) match party plus document number in the client's
  number fields (Reference, voucher number, or a whole token in narration);
  another family recording the same document needs attention.
- `tag` plans (statements) treat any other voucher on the same day with the
  same bank line as possibly existing, unless the server proved it a distinct
  sibling transaction.
- `counterpart` plans (a Contra's lone leg) are covered by one Minkops transfer
  already holding both lines; an untagged one holds.

A `strict` fence encrypts and fsyncs the intent under the app profile
(`statement-manifests`) before importing;
`retry_after_read` lets a later explicit Retry save import only after a fresh
read. Within one attempt an import is never repeated, and only an exact readback
of every line, allocation, date and voucher type is accepted. The server sends
every plan exactly as approved and refuses retired formats, so a run approved
before protocol 5 must be started again.

Bill and statement records arrive as `tally.write` jobs, one at a time per PC,
from the client's runs. A `tally.supplier` job creates one approved GST creditor:
it is imported only when no ledger has its name, so a retry after a lost
acknowledgement reads back the ledger it created, and the server accepts it only
when the readback carries every approved statutory and mailing value. A
`tally.sync` job collects the books read-only, in the pages the server asks for
(see [the rebuild design](rebuild/design.md#sync-protocol)). See [Statement Entry](statement-entry.md)
for routing, balances, review and recovery. The distributed Windows x64 installer remains an unsigned
release candidate; existing unsigned-release disclosure applies.
