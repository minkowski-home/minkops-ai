# Plan: Tally discovery from open companies (companion 0.7.0)

Status: proposed, 14 Oct 2026. Source: production investigation of the Sachin
Infra demo on PC `Prahlad-Gadhwal`. When implemented, fold the final contract into
[source discovery](source-discovery.md) and [Windows app](windows-app.md), record
the decision in [decisions log](decisions-log.md), and delete this file.

## 1. Field evidence

### Customer environment (confirmed on the PC)

| Fact | Value |
| --- | --- |
| Edition | TallyPrime **Edit Log**, local desktop icon (not Remote Desktop) |
| Executable | `D:\TALLY PRIME\tally.exe` (outside `Program Files`) |
| Other processes | `tallygatewayserver.exe`, `tallyscheduler.exe` (always running) |
| `tally.ini` | `Data=D:\TALLY PRIME\SACHIN INFRA ORIGINAL DATA`, `Load=100000`, `Client Server=None`, `ServerPort=9000`, `Enable ODBC Server=Yes` |
| HTTP | `http://localhost:9000` answers `TallyPrime Server is Running` while Tally is open |
| Companies | Many, password-protected, organised in several folders on `D:` |

`Company on Disk` for the configured data folder (captured with the companion's own
read-only XML requests):

| Number | Company | Open | Status |
| --- | --- | --- | --- |
| 100000 | Sachin Infra (2026-27) | Yes | |
| 100001 | Sachin Infra (2017-18) | No | `Migration Required`, `ISTASKCREATIONPOSSIBLE=No`; cannot be opened |
| 100006 | Sachin Infra (2023-24) | No | Password |
| 100007 | Sachin Infra (2024-25) | No | Password |
| 100008 | Sachin Infra (2025-26) | No | Password |

### Production timeline (UTC, 14 Oct; `desktop_jobs`, `discovery_runs`, `task_events`)

| Time | Job | Outcome |
| --- | --- | --- |
| 06:57 | `tally.probe` on `Prahlad` | Failed: wrong machine (user's Remote Desktop session; device later revoked) |
| 07:05:07 | `tally.probe` | Succeeded: `Sachin Infra (2026-27)` |
| 07:05:33 | discover `d969e02d` | "Tally needs attention… close Tally" (19 s) |
| 07:06:28 | discover `2ce62ea3` | "Tally installation was not found" (6 s) |
| 07:17:00 | discover `853f8447` | "Tally company scope could not be verified" (9 s) |
| 07:32:56 | discover `dd0c0ab3` | "Close Tally" (16 s) |
| 07:36:06 | discover `733d11d0` | "Not installed" (3 s) |
| 07:44:52 | discover `6f14f705` | "Close Tally" (16 s) |
| 07:45:42 | discover `d7435f69` | "Not installed" (3 s) |
| 07:46, 07:47 | `tally.probe` ×2 | "Tally is not responding" (27–30 s) |

The probe diagnostics (`%APPDATA%\Minkops\tally-diagnostics\{64a6a934…,1d109e09…}.json`)
record `error: "fetch failed"`, `process_disappeared: true` and no crash events:
Tally was closed at that moment (the user had just confirmed its Quit prompt).
API, worker, scheduler and database behaved correctly throughout.

Ruled out: Edit Log edition (process is `tally.exe`), Remote Desktop, ODBC/port
settings.

## 2. Root causes

| # | Cause | Code |
| --- | --- | --- |
| RC1 | Discovery requires **every company on disk** to be open, so a partially loaded Tally triggers close-and-restart. | `ensureTallyDiscovery`, `tally-recovery.js:141-168`; `client-context.js:70-112` |
| RC2 | Close waits 10 s; Tally's Quit confirmation takes a human longer, so success is reported as failure. | `CLOSE` script, `tally-recovery.js:418-423` |
| RC3 | A closed Tally is located only via App Paths and `Program Files\TallyPrime`; `D:\TALLY PRIME` is missed and reported as "not installed". | `INSTALLATION` script, `tally-recovery.js:380-393` |
| RC4 | Restart cannot produce the full scope in real practices: passwords are a handoff, `Migration Required` companies never load, `/LOAD:<n>` works only inside the single `Data=` folder, and >50 companies on disk always fails. | `startupCompanies`, `readCompanyList` |
| RC5 | Check connection uses a different contract from discovery (open companies only), so it passes when discovery fails. It also maps **any** error to "Tally is not responding" and attempts a Tally restart. | `worker.js:38-40`, `tallyProbe` via `recoveringTallyRequest` |
| RC6 | Diagnostics keep only `fetch failed`, not `error.cause.code`, so refused port vs timeout vs reset is lost. | `recoveringTallyRequest` `diagnose` |
| RC7 | The companion has no auto-update, so every field fix requires a manual reinstall at the client. | `apps/windows-app/package.json` |
| RC8 | Progress text is mis-encoded (`sourceâ€¦`). Server-only fix. | `platform/src/minkops_platform/discovery.py:364` |

RC1 originates from the Pradeepraj Infra decision ([decisions log](decisions-log.md),
"Company on Disk"): a company open in Tally was silently lost after a crash restart.
The fix below keeps that protection without requiring every company on disk.

## 3. Target contract

**Discovery reads the companies open in Tally. It never closes, restarts or
locates Tally for discovery.** Users open companies and enter passwords in Tally,
as they already do; Minkops does not handle Tally credentials.

1. **Scope = open companies.** Preflight reads `Company` (open) and `Company on
   Disk`. Open companies are collected. Disk companies that are not open are
   reported as *not included* with their native status (e.g. `Migration
   Required`); they do not make the package partial and impose no cap.
2. **Completeness protection (replaces "all on disk").** A confirmed discovery pins
   its company scope (already fingerprinted by `_tally_authority`). On the next
   run, a previously confirmed company that is not open makes the package partial
   and raises one attention item: "Open *Sachin Infra (2025-26)* in Tally"
   with **Refresh** / **Do nothing**. Scope changes during collection remain
   partial, as today.
3. **Crash recovery only.** `recoveringTallyRequest` keeps its single restart for a
   process that disappears mid-collection, using the executable observed running
   in that job. If the restart lands on a login screen, it is a handoff, as today.
4. **Cap applies to collected companies** (50), not to the disk folder.
5. **Compatibility.** Discovery plans are negotiated by `X-Minkops-Plan-Version`.
   Companion 0.7.0 advertises the open-scope capability; the server records the
   companion version per device and the console shows "Update Minkops on this PC"
   for older companions instead of dispatching a job that will loop.

Not in scope for 0.7.0: a company picker in the web app (open companies already
express the choice), migrating old Tally data, multi-machine/Tally Server access.

## 4. Changes

### A. Connector and companion (`connectors/desktop`, `apps/windows-app`)
- `ensureTallyDiscovery` → `tallyPreflight(config)`: read-only; returns
  `{state, open, notIncluded}` with no stop/start. Remove `closeTallyProcess`, the
  `CLOSE` script and the discovery restart path (net LOC reduction).
- `client-context.js` `companyScope()`: scope from open companies; carry
  `notIncluded` into the snapshot for review display.
- Installation lookup (crash recovery only): prefer the executable last observed
  running (`state.tally_startup`), then App Paths, then Uninstall
  `InstallLocation`, then `Program Files`. When absent, say "Open Tally, then retry"
  instead of "Install TallyPrime".

### B. Check connection = discovery preflight
- `tally.probe` calls `tallyPreflight` without the recovery transport, so it never
  starts Tally and cannot disagree with discovery.
- Typed, user-safe outcomes, decided from `error.cause.code` and a read-only
  process check:

  | State | Message |
  | --- | --- |
  | `not_running` | "Tally isn't open on this computer. Open it, load your companies, and check again." |
  | `port_closed` | "Tally is open but not accepting connections. In Tally: F1 → Settings → Connectivity, enable port 9000." |
  | `busy` (timeout) | "Tally is busy. Finish any open prompt or company login, then check again." |
  | `no_company` | "Open at least one company in Tally." |
  | `ready` | Lists open companies and not-included companies with status |
- `worker.js`: stop overwriting connector errors; pass through messages flagged
  user-safe, keep the generic fallback for everything else.
- Diagnostics record `cause.code` and elapsed time.

### C. Server and web (`platform`, `apps/solution-api`, `apps/solution-web`)
- `discovery.plan`: label "Companies open in Tally"; require plan capability v3.
- Pinned-scope comparison and attention item on missing confirmed companies.
- `desktop_devices.companion_version` (migration) from a request header; console
  update prompt for < 0.7.0.
- Review screen: open companies collected; not-included companies listed in a
  muted section with status.
- RC8 encoding fix (can ship immediately, server only).

### D. Auto-update (last manual install)
- `electron-updater` with a generic feed on Firebase Hosting next to the existing
  installer; blockmap differential downloads to protect the hosting transfer
  budget (installer ~103 MB).
- Download in the background; install on quit or when idle, never while a job is
  claimed or a save receipt is pending.
- Installer is unsigned today: updates are still SHA-512 verified, but code signing
  should be scheduled to remove SmartScreen friction.

## 5. Tests (write first)

Connector (`node --test`):
- Open 1 of 5 disk companies (one `Migration Required`): collects 1, reports 4 not
  included, never calls stop/start, package complete.
- Tally closed: preflight `not_running`; no spawn attempted.
- `ECONNREFUSED` with `tally.exe` running → `port_closed`; timeout → `busy`.
- Previously confirmed company not open → partial with missing company listed.
- Mid-collection crash still restarts once from the observed executable.
- Install lookup finds `D:\TALLY PRIME\tally.exe` from remembered state and
  Uninstall `InstallLocation`.
- Probe errors surface their typed message through `worker.js`.

Server (`pytest`): plan v3 gating, companion version recording, pinned-scope
attention item, review payload, encoding regression.

Live (Windows VM before release): TallyPrime Edit Log installed under `D:\`, five
companies (one unmigrated), two passwords, Quit confirmation enabled; run Check
connection and discovery with 1, 3 and all companies open, plus Tally closed.

## 6. Delivery

Branch `platform-desktop/tally-open-company-scope`, merged to `staging`. Commits:
1. RC8 encoding fix (server).
2. Typed preflight + Check connection (B), tests first.
3. Open-company scope in discovery; remove close/restart path (A).
4. Pinned scope comparison, attention item, plan v3, companion version (C).
5. Auto-update (D).
6. Docs: source-discovery, windows-app, decisions-log STAR entry; delete this plan.
Release companion 0.7.0 through the existing installer, then deploy the API.

## 7. Next-meeting runbook (Prahlad-Gadhwal)

1. Install Minkops 0.7.0 over 0.6.10 (last manual install; sign-in is kept).
2. Open TallyPrime Edit Log from its desktop icon; open **Sachin Infra (2026-27)**
   and enter its password. Optionally open other years to include them.
3. Check connection: expect *ready* with 2026-27 open and four companies not
   included (2017-18 shown as Migration Required).
4. Run Source Discovery, keep Tally open; expect *completed*, then confirm review.
5. Operator check: `discovery_runs.state = 'completed'`, `catalog.partial = false`.
