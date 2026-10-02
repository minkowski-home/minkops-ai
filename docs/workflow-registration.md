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

Executable definitions now declare an `execution` object in `workflow.json`:
`environment: openai_hosted`, `model`, `python_packages`, a relative
`instructions` path, explicit relative `resources`, and an absolute
`result_path` inside `/workspace/outputs/`. Network access remains disabled for
the current file workflows. An execution descriptor does not grant tool access;
no business-system MCP binding is introduced by this refactor.

Launch persists `config.execution_snapshot`: format version, workflow and
definition identity, execution settings, skill manifest name/description,
UTF-8 resource contents, and a SHA-256 digest. The skill entrypoint, turn
instructions, workflow descriptor, configuration/output schemas, and declared
helpers are bundled together. Supporting scripts and references must be listed
explicitly; directory scans would risk including credentials or evaluation
answers. Both the uploaded skill archive and execution instructions use the
snapshot, never newer checkout files. Provider skill metadata comes from the
pinned SKILL.md YAML frontmatter, not the product's workflow description.

Definition-only registration remains supported without an execution descriptor;
launching an Accounts run requires one. Existing active sessions can be
reconciled without resubmitting input. Legacy queued runs without a complete
execution snapshot fail with an explicit relaunch message rather than silently
adopting new instructions. Drain legacy queues before changing worker versions.

## Verification

```sh
uv run --all-packages python -m unittest discover -s platform/tests
```

Registration integration checks use a temporary schema on the database supplied
through TEST_DATABASE_URL. They exercise repeat registration, preservation of
operator defaults, incompatible updates, and tenant scoping. No live Agents API
calls are made.
