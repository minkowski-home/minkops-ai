# Windows app and companion (MIN-117)

The Windows 10/11 x64 app loads the same deployed React application as the web
app, reusing verified email/password accounts, memberships, workflows, reviews
and task history. The native host adds folder selection and a tray companion;
one workspace/account is connected per running installation.

This revision builds companion 0.9.1 (plan protocol 5; see its contracts below),
the release recorded in `windows-release.json`. The server refuses companions
older than 0.9.0. The companion works only with the
companies open in the user's Tally, reports typed session states, sends
diagnostics and updates itself. Core Tally discovery uses HTTP/XML exports and
needs no ODBC driver. Windows 10 device testing was deferred by the owner;
compatibility is retained.

## Local capabilities

| Operation | Desktop | Web with a connected PC | Authority |
| --- | --- | --- | --- |
| Check Tally | Yes | Yes | Fixed, read-only company export to `127.0.0.1:9000` |
| Discover Tally and Excel | Yes | Yes | All loaded companies, voucher period and explicitly granted folders; versioned client context |
| Connect a folder | Native picker | Open desktop to grant it | Explicit local selection; snapshots must match the uploaded source |
| Refresh a connected folder | Yes | Yes | Owned device/source binding; limited supported files |
| Save approved Tally vouchers | Yes | Yes | Confirmed company/ledger references, immutable approved plan, durable intent before import and exact readback |
| Existing hosted workflows | Yes | Yes | Existing server and OpenAI-hosted Agents API contracts |

This version adds bounded native operations, not customer-machine agent hosting
or a general remote shell. See [Source discovery](source-discovery.md),
[Bill entry](bill-entry.md) and [Statement entry](statement-entry.md). Initially open Tally with its HTTP server enabled on port 9000; discovery must
see every company the run may use. A company listing is a connection
check, not verification of financial writes.

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
are not automatically dispatched twice on lease expiry. An explicit new save
request can recover an interrupted attempt: hashes distinguish unchanged,
already-saved and externally-edited workbooks. A persisted receipt is retried
before further work. Domain side effects and job state commit atomically.

The companion polls outbound HTTPS every four seconds. It opens no inbound
server and needs no browser loopback exception, firewall port or router
forwarding. Future mobile clients can use the same server-owned tasks and
request bounded work on an authorized connected PC.

Presence is independent of job dispatch: authenticated companion traffic updates
`last_seen_at`, and busy workers send a bounded, single-flight heartbeat without
claiming another job or extending its lease. Dispatch and confirmed discovery
archiving are serialized, so slow archive transfers cannot overlap each poll.
Completion uploads have a two-minute client budget; control requests retain
45 seconds, and failed deliveries retain their durable receipt. Release the API
heartbeat endpoint before rolling out a companion that calls it.

## Tally session, diagnostics and uncertain writes

Tally belongs to the user. The companion never starts, closes, restarts or locates
Tally, never handles company passwords and never chooses data folders; it works
with the companies the user opened, from any folder (`connectors/desktop/src/tally-session.js`).
Check connection, the discovery preflight and the check before every bill save
share one read-only classifier, so they cannot disagree. It reads the open
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

Typed messages pass through job receipts verbatim; untyped errors keep a generic
fallback. Before each save the company must be open and match the discovered GUID;
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

Bill saves use the run's pinned purchase voucher type, chosen from discovered types
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
Remote Desktop session. The console shows them, warns about Remote Desktop, and the
server refuses Tally work for companions older than 0.7.0 with "Update Minkops on
*PC*". A PC that has not polled yet may queue work.

`node scripts/verify_tally_session_live.mjs [port] [company] [guid]` prints the
typed state on a Windows PC without changing Tally, for rehearsals.

Versioned discovery packages are saved locally as described in
[source discovery](source-discovery.md), alongside the authoritative server copy.

## Build and run

Run `db/migrate.py` before starting a new revision; it installs the baseline or
adopts archived upgrade history without resetting run history (see
[database upgrades](../db/README.md)). See [workflow authoring](workflow-authoring.md)
for installation and recovery.

Use Node 24 and the existing Python/uv workspace. From the repository root:

```sh
cd connectors/desktop && npm ci
cd ../../apps/windows-app && npm ci
npm test
npm run build
npm run package:win
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
branch. Install or adopt the final baseline before using bill entry. Use normal
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
Production distribution needs the organization's Windows signing certificate;
without one, builds are unsigned release candidates. The packaged profile uses
`https://app.minkops.com`; release notes must disclose the unsigned status.

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
Downloads are SHA-512 verified; until the installer is code-signed, first installs
still show SmartScreen.

Run `npm ci` in this app before building a release. Its `.npmrc` packages the two
local modules rather than depending on Windows junction traversal, and this
app's lockfile pins their transitive dependencies. After editing either local
module, reinstall before building: packaged copies do not update automatically.

## Progress and review

Task detail leads with a short status, an observed stage and a business summary.
Discovery uses Get ready → Work → Review → Finished; bill entry adds Save;
connection checks/refreshes have their own short stages. Events drive stages,
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
discovery finishes there and reopening shows its result. Catalog exports fetch
only the authorized tenant/run endpoint, use a user-selected `.json` destination,
enforce a size bound, reject symlinks/nonregular files and write through a synced
temporary file with atomic replacement (bounded IPC, not a Chromium download).

Native suites pass on Linux and Windows; Windows skips only a file-symlink test
that requires creation privileges (the same guard runs on Linux). A fresh
Windows 10/11 device matrix, screen-reader audit and signed distribution have
not been verified.

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

Statement rows arrive as `tally.write` jobs, one at a time per PC, from runs of
the client's own statement workflow. See [Statement Entry](statement-entry.md)
for routing, balances, review and recovery. The distributed Windows x64 installer remains an unsigned
release candidate; existing unsigned-release disclosure applies.
