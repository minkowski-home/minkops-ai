# Source Discovery: reviewed client schema context

Source Discovery 0.6.0 collects structure and headers. It does not export business
records, balances, tax values, formulas, comments, hyperlinks or named constants.
The new header-only folder grant requires Windows companion 0.4.0.

Pair a PC with the production HTTPS console, grant an explicit Excel folder,
and select Tally, Excel or both. For Tally, open the requested company, enable
its HTTP/ODBC services and install the matching **64-bit Tally ODBC driver/DSN**.
The adapter accepts only company and port, connects to loopback, and accepts no
caller-provided hostname, SQL, XML, TDL or script.

## Tally client/server coverage

The adapter calls ODBC GetSchema('Tables') and GetSchema('Columns') for each exposed
table, without querying records. The HTTP company probe checks availability.
The catalog contains all tables exposed by this installation's ODBC provider and
column metadata. Coverage is explicitly exposed_top_level_methods or not_exposed;
this does not promise every nested method or custom UDF. See
[Tally's ODBC exposure boundary](https://help.tallysolutions.com/odbc-integrations/).

Server-backed data is compatible in principle: a local Tally client can open
server-backed company data and expose its own integration service.
[Company access](https://help.tallysolutions.com/tally-prime-server/application-configuration-tallyprime-server/accessing-company-data-from-tallyprime-server/)
and [XML integration](https://help.tallysolutions.com/xml-integration/) document
those capabilities. This is an inference; the customer's exact LAN topology
still needs an acceptance test. If integration exists only on the server, run
the companion on that authorized integration PC. Arbitrary remote connections
are outside this connector's scope.

## Excel headers and catalog ownership

The companion projects selected .xlsx files into fresh header-only workbooks
before upload. Named-table headers/ranges are authoritative; a plain sheet's
candidate header in the first ten rows requires review. Backend validation rejects
non-header values and canonicalizes bytes. Sheet names, table columns/ranges and
merges remain; original bytes and local paths stay on the PC. Browser-only folder
selection cannot substitute original workbooks for this native discovery grant.

Immutable JSON catalogs live in PostgreSQL discovery_runs.catalog, scoped by
tenant, operator, registered device and source. Confirmed destination mappings
live in the tenant's account_catalogs. Optional JSON download exports the catalog;
it is not a global configuration file.

Production uses durable PostgreSQL. Core definitions ship under employees/ in
the immutable image; additive client instructions/defaults ship under solutions/.
Client observations belong in the tenant database, not core definitions or
container disk. Every client installs its own bindings and collects its own
catalogs. See [workflow authoring](workflow-authoring.md).

## Consuming workflows

Dependent workflows resolve a confirmed, complete compatible catalog and pin
relevant JSON context in their run. Bill Entry selects company, ledger and
voucher-type schema for Tally, or reviewed Excel mappings. Context arrives
automatically; arbitrary uploaded JSON is not a launch input. Its fixed Purchase
adapter and independent write checks remain authoritative. Schema improves
interpretation; it does not create an unrestricted write adapter or authorize
financial writes.

Bill Entry separately queues a bounded tally.references job to read current
company identity, ledger names/parents and voucher types from the paired PC.
Paid execution waits for it. These operational references belong to the bill
run, never the schema catalog. Continuation refreshes references and pins the
refreshed schema independently of successful siblings; a changed company GUID
blocks it. Writes still require approval and readback. Header-only Excel
registrations require an authorized real-file refresh before destination writes.

## Bounds, compatibility and verification

Tally metadata is capped at 500 tables, 2,000 columns/table, 100,000 columns total,
16 MB helper output and a 60-second metadata timeout. The old **3 MB / 10,000
records** bound applies only to runtime reference exports, not Source Discovery.

Excel parser bounds: 5 MB/workbook, 100 sheets, 10,000 rows and 250,000 cells/sheet,
500 columns and 50 MB expanded ZIP. These protect local allocation; those rows
are not uploaded. Hosted mapping retains its 45-workbook / 8 MB input budget.
Narrow unsupported selections explicitly.

Unavailable sources yield visible partial scans; successful schema remains
downloadable. Partial or unreviewed catalogs block consuming workflows. Tenant
ownership, device revocation, leases, replay and hashes are enforced outside the
model. Legacy catalogs remain readable; new launches reject record-collection
depths.

Regressions cover metadata-only calls, projection privacy, receipt validation,
live-reference gating, retry identity/pinning and tenant ownership. Real Windows
ODBC returned 275 exposed tables on the current PC (Ledger: 400 columns).
The historical 6 October installed RC predates this change. Rebuild 0.4.0 and
verify clean Windows 10/11, driver-present/missing, remote-server topology and
production HTTPS, then repeat hosted mapping and reviewed-write proof.
See [deployment and MIN-123 closeout](deployment-min-123.md).
