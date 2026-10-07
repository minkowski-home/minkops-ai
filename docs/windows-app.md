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
| Existing hosted workflows | Yes | Yes | Existing server and OpenAI-hosted Agents API contracts |

This version adds bounded native operations, not customer-machine agent hosting
or a general remote shell. See [source discovery](source-discovery.md) for MIN-118.
Bill-to-Tally writes and bank statement logic remain MIN-119/120. Tally must be
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
its companion; web users can revoke a PC in Connections. An operation already
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

This architecture branch is based on `apps/windows-app` commit `c3b050c`.
Its shared API/UI now uses installed workflow bindings and shared dispatch;
native folder grants, discovery, receipts and tray execution keep their existing
contracts. Apply migrations through `0009_workflow_bindings` before starting
this revision. Later Bill entry/Tally financial-write branch work is not included.
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
branch. Apply migrations 0005–0007 before connecting devices. Use normal
production email verification and secure session settings; never production
`AUTH_DEV_MODE` or demo seeding.

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

User-facing UI, picker, clean install, tray and Windows 10/11 visual/accessibility
checks remain Todo in [MIN-122](https://linear.app/minkops/issue/MIN-122).
