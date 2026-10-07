# Windows app and companion (MIN-117)

The Windows 10/11 x64 app loads the same deployed React application as the web
app, reusing verified email/password accounts, memberships, workflows, reviews
and task history. The native host adds folder selection and a tray companion;
one workspace/account is connected per running installation.

## Local capabilities

| Operation | Desktop | Web with a connected PC | Authority |
| --- | --- | --- | --- |
| Check Tally | Yes | Yes | Fixed, read-only company export to `127.0.0.1:9000` |
| Discover Tally and Excel | Yes | Yes | Selected company/port/categories and explicitly granted local folders; server-owned versioned catalog |
| Connect a folder | Native picker | Open desktop to grant it | Explicit local selection; snapshots must match the uploaded source |
| Refresh a connected folder | Yes | Yes | Owned device/source binding; limited supported files |
| Save approved Excel entries | Yes | Yes | Accounts approval, before/after hashes, backup, atomic replacement and saved-byte verification |
| Save approved Tally bills | Yes | Yes | Confirmed company/ledger references, immutable approved Purchase plan, read-before-write and exact readback |
| Existing hosted workflows | Yes | Yes | Existing server and OpenAI-hosted Agents API contracts |

This version adds bounded native operations, not customer-machine agent hosting
or a general remote shell. See [source discovery](source-discovery.md) for MIN-118.
Bill-to-Tally writes are covered in [MIN-119](bill-entry.md); bank statement logic remains MIN-120. Tally must be
open, with its HTTP server enabled on port 9000. A company listing is a connection
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

## Build and run

The consolidated branch retains Windows baseline `c3b050c`, the shared workflow
architecture, and Bill Entry's financial-write work through `3dc6552`. Its API/UI
uses installed bindings and shared dispatch, including independent bill sessions,
native Tally reconciliation, and verified Excel/Tally writes. Apply all pending
migrations through `0011_complete_branch_convergence` before starting this
revision. Either predecessor database can upgrade without resetting run history.
See [branch convergence](branch-convergence.md) for the tested paths.
See [workflow authoring](workflow-authoring.md) for installation and recovery.

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
branch. Apply all migrations through 0011 before using bill entry. Use normal
production email verification and secure session settings; never production
`AUTH_DEV_MODE` or demo seeding.

For an installed local RC, `Minkops.exe --local-demo` uses the fixed
`http://127.0.0.1:3018` origin and isolated `Minkops Local Demo` profile. The normal
packaged profile remains HTTPS-only. This switch grants no general URL override.
The local profile retains encrypted registration credentials and folder grants
across install/restart; keep the local API/UI/worker services running for testing.

Configure an edge request limit of at most 42 MB on the base64 folder receipt
route, with smaller limits elsewhere. Services/native adapters enforce 100
supported files, 5 MB per file, 30 MB per snapshot and folder containment.
Production distribution needs the organization's Windows signing certificate;
without one, local builds are unsigned test installers. No production deployment
or automatic updater is introduced.

## Progress and review

Task detail leads with a short status, an observed stage and a business summary.
Discovery uses Get ready → Work → Review → Finished; bill entry adds Save;
connection checks/refreshes have their own short stages. Events drive stages,
with no simulated percentage or ETA. Failures remain at the last observed
stage. Labels and outlined icons work independently of color or animation.

Review shows actual sheet/entry counts and unclear destinations. Editable
business values remain visible; source evidence and activity are expandable.
All four themes and responsive layout are shared. Accounts alone decides when
all workbooks are verified; one native job cannot complete a multi-workbook run.

## Verification

Tests use real PostgreSQL and sessions for ownership, tenant isolation, CSRF,
revocation, rotation, concurrent claims, request/receipt replay, invalid folder
snapshots, approval, corrupt saved bytes, read recovery and cancellation.
Native tests cover fixed Tally XML, limits, folder containment (Windows junctions
and Linux symlinks), backup-before-write, external edits, already-saved recovery,
receipt replay and IPC origin/frame isolation.

For an opt-in Windows-native HTTP smoke against a disposable localhost API with
`AUTH_DEV_MODE=1`, set `MINKOPS_SMOKE_URL=http://127.0.0.1:8117` and run
`npm run test:http`. It creates a dummy workspace and temporary files, refreshes
through HTTP/PostgreSQL, loses a server acknowledgement, recreates the worker,
replays the receipt, checks Tally availability and revokes the PC. It makes no
accounting writes or paid agent calls.

Set `MINKOPS_SMOKE_EXPECT_COMPANY` to an open test company's exact name to require
a successful live Tally export and verified server task completion. The live
Windows check on 5 October 2026 returned `Minkops Test`, with queued → executing
→ completed observations. Typed XML name elements are parsed as text; malformed
nested names are rejected rather than converted into misleading object strings.

On 6 October 2026 the unsigned 0.3.1 NSIS installer was installed successfully on
Windows 11 Pro (build 26300) and launched against the shared production UI build. MIN-122's
local sweep covers four themes, native folder selection, bounded JSON catalog
Save As, missing-supplier Needs Attention, independent clarification, approve/
hold/reject/edit controls, duplicate alerts, source previews and web/desktop task
synchronization. Closing the main window leaves the native worker in the tray;
a web-requested discovery finishes there and reopening shows its result.

Catalog exports fetch only the authorized tenant/run endpoint, use a user-selected
`.json` destination, enforce a size bound and reject symlinks/nonregular files.
The connector writes through a synced temporary file and atomic replacement.
The earlier Chromium download path left an incomplete temporary file in the
installed shell; the explicit bounded IPC export fixes that failure.

Evidence lives in the RC's OneDrive `evidence` and `schema` folders. Native suites
pass on Linux and Windows; Windows skips only a file-symlink test that requires
creation privileges (the same guard runs on Linux). A fresh Windows 10/11 device
matrix, screen-reader audit, production hosting and signed distribution have not
been verified by this local sweep.
