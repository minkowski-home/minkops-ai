# Workflow registration and run configuration

## Definition and execution boundary

Shared workflow definitions are Git-versioned under `employees/`. Tenant
defaults are PostgreSQL `workflows.config_values`, validated against
`tenant-config.schema.json`. Per-run choices have a separate schema and are
not stored as tenant defaults. The UI edits tenant defaults and per-run selections. See [Accounts desk](accounts-desk.md)
for the implemented runtime and its separate agent proposal schema.

Bill entry's output contract has two layers. The Git-versioned output schema
describes the result envelope, evidence, findings, and review state. Discovery
and confirmation establish the business field schema and destination mapping
in the catalog. Each bill run pins catalog_version, schema_id, and schema_version.
`validate_output` validates the envelope and each record's data against a
confirmed schema snapshot supplied by trusted catalog lookup. It also rejects
mismatched versions and external schema references. This does not validate
arithmetic, evidence truth, approval, or artifact existence.

The mock seed installs Source discovery and Bill entry for `mock-tenant`,
owned by Accounts desk and active only for the mock tenant. The existing frontend maps the
`mock-client` URL to this tenant. Registration preserves existing settings and
status, rejects incompatible schema updates, and increments config_version
only when the tenant configuration schema changes. This counter is not the
workflow definition version.

## Local registration

From the repository root:

```sh
uv sync --all-packages
uv run --all-packages python db/migrate.py
uv run --all-packages python db/seed_demo.py
```

Set DATABASE_URL to the local development database as described in db/README.md.
The seed changes the demo account password; supply DEMO_PASSWORD to retain a
chosen local password. Never run the demo seed against a deployed database.
`db/fixtures/mock_workflows.json` supplies initial database defaults only.

## Run resolution

`minkops_platform.workflows.resolve_run_config` merges workflow run defaults,
tenant defaults, then run selections. Schema validation rejects unknown
settings and unsupported formats. Trusted callers supply authorized source
and destination IDs and any mandatory review policy; requests cannot grant
themselves permissions. The Accounts API validates tenant-scoped file IDs, confirmed catalog versions,
relative paths and source capabilities. The browser resolves children through
its granted directory handles; absolute paths and parent traversal are rejected.

`db/fixtures/mock_workflow_runs.json` contains example selections, not actual
registered files, catalogs, connections, or destinations.
The example business schema ID/version is also a placeholder; no confirmed
business schema has been created and no discovery run is implied. Browser folder grants bind the synthetic sources explicitly. Ground truth and PR Infra files are excluded.
No connections or source permissions are provisioned by this seed.

Before execution, persist the resolved configuration, definition version,
catalog version, actor, and authorized resource bindings with the run. The
Accounts API persists these alongside agent output schema and instructions before
launch. Recording definition versions there avoids
confusing Git releases with editable tenant settings.

## Verification

```sh
uv run --all-packages python -m unittest discover -s platform/tests
```

Registration integration checks use a temporary schema on the database supplied
through TEST_DATABASE_URL. They exercise repeat registration, preservation of
operator defaults, incompatible updates, and tenant scoping. No live Agents API
calls are made.
