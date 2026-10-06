# Client-PC source discovery (MIN-118)

Source discovery is enabled for the mock client. PR Infra has no bindings or
client rules in this pass. The same shared console runs in the browser and the
Windows 10/11 x64 companion. A browser can launch discovery on its operator's
registered PC while that companion runs in the tray.

## Connect a client's PC

1. Install Minkops, sign in with a verified email/password account, open the
   workspace's **Connections**, and select **Connect this PC**.
2. In **Source discovery**, select that PC. Connect an explicit Excel folder
   from the desktop app. Native paths and folder grants stay encrypted on the
   PC; the server stores source/device identities and authorized snapshots.
3. Select Tally, Excel or both. For Tally, enable its HTTP service, open the
   required company, and enter its exact name and port (default 9000).
   Connections are restricted to that PC's loopback address; a caller cannot
   supply a hostname, raw XML, TDL, script or shell command.
4. Choose discovery depth. **Everything needed for Bill Entry** is the default.
   The Tally category checkboxes narrow reference collection. Excel scope is the
   selected folders; reconnect a focused folder to narrow a large source.
5. Run discovery, review the observed sources and proposed Excel mappings, and
   confirm. The first confirmation is explicit. Unchanged refreshes retain the
   reviewed mappings, including when ordinary Excel rows are added.

The client needs no developer Node/Python environment or repository checkout.
The installer bundles the native adapters. The server needs PostgreSQL, the API,
the Accounts worker and its OpenAI credentials. Local execution here means
bounded Tally/Excel access on the selected PC; business reasoning stays in the
existing OpenAI-hosted Agents API skill workflow. General local shells and
scheduling are outside this pass.

## Catalog contract and recovery

`employees/accounts-desk/workflows/source-discovery/collection-config.schema.json`
defines collection configuration. Workflow version 0.5.0 pins that schema in
the hosted skill bundle. Canonical catalogs live in tenant-scoped PostgreSQL
`discovery_runs`; each run is an immutable version identified by its UUID.
The download includes collection time, device ID, depth, source identities,
availability, workbook hashes, local observations, reference records and reviewed
mappings. **Download source catalog** exports JSON: the installed Windows app
uses a native Save As dialog and a bounded atomic file writer; the browser uses
its normal download. Automatic local JSON copies are not created.

Tally uses fixed, read-only collection exports scoped with `SVCurrentCompany`,
following [Tally's XML collection contract](https://help.tallysolutions.com/understanding-tally-xml-tags/).
The default categories cover company/tax settings, account groups, ledgers,
voucher types, stock items/groups, units, locations, cost centres/categories and
currencies. XML identifiers remain strings. Nested GST/tax settings are retained
rather than flattened away. Empty collections are distinct from failed reads.

ExcelJS reads actual .xlsx structures on the PC: worksheets, named tables and
their ranges/header rows/columns, defined names, merged ranges, formulas, typed
sample values and reference rows. Formulas are observed, never executed. The
server checks workbook hashes and sheet/table coverage against the bytes before
accepting the receipt. Hosted mapping proposals use those observations and
workbook snapshots; existing Accounts validation remains authoritative for
approved destinations and future writes.

Openpyxl writes valid package-absolute table relationships that ExcelJS 4.4
cannot resolve ([upstream issue 1468](https://github.com/exceljs/exceljs/issues/1468)).
The native adapter converts those relationship URIs to equivalent relative URIs
in an in-memory reader copy. Original file bytes, hashes, uploads and save
approvals remain unchanged. This is covered by a regression and a live refresh
of the demo workbook after an openpyxl write and named-table expansion.

Each source/category has visible reading, collected or needs-attention status.
An unavailable Tally company, folder, collection or unsupported workbook yields
observable partial results; successful observations remain downloadable. Partial
scans do not launch paid business mapping and cannot be confirmed. Reconnect the
source and run discovery again. Hosted environment failures keep the collected
catalog and show a failed task; retry is explicit rather than replaying input.
Session cleanup waits between attempts and stops after ten background failures,
retaining the pending status for operator intervention. It never reports a
failed cleanup as success, following the
[hosted cleanup guidance](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted).

Receipt persistence, scoped claims and atomic server transactions handle restarts
and acknowledgement loss. Progress renews the read lease. Revocation stops the
device. Rejected/oversized receipts become visible failed tasks, preventing
silent infinite reclaim loops. Changing server origin requires fresh pairing;
credentials/grants are never carried into a different deployment.

`discovery.require_ready()` is the dependent-workflow gate: require a confirmed,
complete latest catalog containing the selected tools. Excel Bill Entry already
uses it for catalogs produced by native discovery. MIN-119/120 must pin this
version, recheck live source versions and obtain approval before consequential
writes; discovery never authorizes a financial write by itself. MIN-119 now uses
this gate for both Excel and Tally, including another check before dispatch and
native company/ledger version checks before Tally saves. See [bill entry](bill-entry.md).

Limits: 45 Excel workbooks / 8 MB per mapping run, 5 MB per workbook, 10,000 rows
per worksheet, 250,000 cells per worksheet, 50 MB expanded ZIP, and 100 sheets.
Tally reads are capped at 3 MB / 10,000 records per category. Unsupported or
oversized selections require a narrower scope; this is an MVP, not an unbounded
enterprise scan. Native adapters and server receipt transport bound allocation.

## Local demo

The dedicated demo database is separate from regression-test history. Use the
provided demo guide for this workstation. The API and shared UI are running at
ports 8118 and 3018, with the normal Accounts worker and a dedicated database.
Start the bundled `Minkops.exe` with `--local-demo` to use the loopback UI at
`http://127.0.0.1:3018` and a separate encrypted local profile. Other packaged deployments
continue to require HTTPS. Demo account credentials and the synthetic workbook
are supplied alongside the installer, never customer data or server secrets.

On another workstation, deploy or run the server first, configure
`MINKOPS_APP_URL` to its HTTPS origin, then follow the connection steps above.
The local demo establishes runtime behavior, not production hosting readiness.

## Verification

`apps/windows-app/tests/discovery-smoke.mjs` performs real Windows/Tally/Excel
collection against an isolated loopback API and mock client. It creates a small
workbook with suppliers, projects and a purchase register, dispatches through
registered-device claims, posts progress, persists/downloads JSON and checks
receipt replay. `process-live-discovery.py` optionally runs the paid hosted
boundary for one mapping run. `verify-live-discovery.mjs` confirms real proposals
and checks unchanged refresh, unavailable Tally partial results and recovery.
These are opt-in developer tests, not customer onboarding requirements.

Database/API regressions cover ownership, tenant isolation, invalid configuration,
receipt scope/hash validation, stale claims, revocation, readiness gates, mapping
confirmation, ordinary row additions and changed-header review. Native tests run
on Linux and Windows. Installer contents are compared with the compiled bundles.
The 6 October release candidate verified the installed Windows 11 app's visual
flows, native catalog Save As, tray collection and shared web/desktop results.
MIN-122 remains In Progress for the clean Windows 10/11 installation matrix and
production HTTPS profile; see [Windows verification](windows-app.md).

The current mock-client release candidate uses Test Company on this PC and keeps
fixtures, catalog snapshots and evidence in OneDrive outside the repository.
Source discovery retains editable Excel/Tally/Both configuration; Bill Entry
is restricted to Tally for this client. An unchanged confirmed refresh may
satisfy an older pinned run only when its schema fingerprint matches exactly.
Changed, partial or unreviewed discoveries continue to block writes. See
[the release candidate bill proof](bill-entry.md) for paths and verified results.
