# Authoring and installing workflows

A workflow is a repository-owned skill run as tool sessions on the run model.
Minkops owns authorized inputs, durable runs, every check, human review and
verified writes; the model reads, looks things up and proposes. Start from an
existing handler and its tools. Add Python only for a guarantee the application
must enforce, or a lookup the session demonstrably needs.

Runs share the task controls and the configurable active-processing budget; see
[run limits and updates](run-limits-and-updates.md).

## Repository contracts

```text
employees/<employee>/
  employee.json
  workflows/<workflow>/
    workflow.json
    SKILL.md
    tenant-config.schema.json
    run-config.schema.json
    stages/<stage>.md             # instructions for each further kind of session
solutions/<client>/
  solution.ts                     # console identity and optional tenant-slug mapping
  installation.json
  employees/<employee>/binding.json
  employees/<employee>/workflows/<workflow>/variant.json   # optional client procedure
```

`employee.json` defines `key`, `name`, `description`, `config_schema` and
`defaults`; see `employees/accounts-desk/employee.json`. An employee is a product
grouping, not another agent loop.

`workflow.json` (validated by `platform/src/minkops_platform/workflows.py`) declares:

- `key`, `version`, `name`, `description` and `owner`, the employee it belongs to;
- `handler`: the run handler, one key of the closed registry
  `work.HANDLER_MODULES` (`desk.bill`, `desk.statement`). A request never names a
  module;
- `presentation`: the review surface for its records (`desk-review`);
- `instructions` (the skill, with YAML `name` and `description`),
  `tenant_config_schema` and `run_config_schema`, as paths inside the directory;
- `tenant_defaults` and `run_defaults`;
- `sessions`: the `model`, an optional `reasoning_effort` (`low`, `medium`,
  `high`), and optional `stages`, each naming its own instructions. Statement
  entry's `layout` stage is one.

Every file is read from inside the workflow's own directory, without symlinks.
Launching a run pins the session bundle (`runtime/bundles.py`): model, reasoning
effort and every instruction text, with a digest. Later edits never change a run
already launched.

A handler module provides what its runs need:

- `launch`: validate the request and create the run, its items and records;
- `session` and `settle`: the session an item runs, and how its outcome settles
  the item's records (see `platform/src/minkops_platform/lanes.py`);
- `summarize`, `detail`, `decide`, `approve_ready`, `written` and `stopped`, for
  the runs API, decisions, native write receipts and Stop.

Its tools are MCP-shaped contracts (`runtime/tools.py`): a name, a description
and an input schema, checked before the handler runs. Tools are read-only or
record a proposal for the run's own review, and they scope themselves to the run.

## Client composition and installation

`solutions/<client>/installation.json` selects an **existing** tenant and its
employees; for example, `{"tenant": "mock-tenant", "employees": ["accounts-desk"]}`.
Each employee's `binding.json` lists its workflows:

```json
{
  "workflows": [
    {"key": "statement-entry", "status": "active"},
    {"key": "bill-entry", "status": "active", "defaults": {"review_mode": "all_outputs", "company_mode": "infer"}}
  ]
}
```

Apply migrations, then validate and install with the uv stack:

```sh
uv run --all-packages python db/migrate.py
uv run --all-packages python -m minkops_api.install_workflows mock-client --validate-only
uv run --all-packages python -m minkops_api.install_workflows mock-client --actor-email admin@example.com --dry-run
uv run --all-packages python -m minkops_api.install_workflows mock-client --actor-email admin@example.com
```

Installation is a server administrative operation on `DATABASE_URL`.
`--actor-email` names an existing verified tenant or platform administrator for
authorization and audit; it is not browser authentication. Validation checks
ownership, paths, schemas, defaults and handlers. A dry run also checks the
tenant's current state, then rolls its transaction back.

Installation creates no tenants or users and grants no file, device or company
access. It keeps existing operator settings and statuses, rejects incompatible
schemas atomically, and bumps configuration versions only for schema changes.
Binding statuses and defaults initialise new rows only. Removing a reference
deletes no history; pause a workflow to withdraw it.

The web build discovers `solutions/*/solution.ts` automatically: a new client
needs a rebuild, not a registry edit. If the public solution ID differs from the
tenant slug, set `tenantSlug` in `solution.ts` to match `installation.json`.

## Client procedures

Core workflows hold only rules that generalise. A client's own procedure lives
in a variant under `solutions/<client>/employees/<employee>/workflows/<workflow>/`,
selected by the binding's `"variant": "variant.json"`:

```json
{"version": "1.0.0", "instructions": "client-instructions.md", "defaults": {"review_mode": "only_exceptions"}}
```

Its instructions are appended to the core skill under "Client procedure". Its
defaults apply over the core's, and the binding's over both. A variant may also
rename the workflow. It never replaces the handler, schemas, tools or checks.
Runs pin the core and variant versions with the composed text, so another
client or a later edit cannot change pending work.

Extensions go in three places:

1. Procedure, in skills and client variants under `employees/` and `solutions/`.
2. Handlers, tools and deterministic checks under `platform/`, enforced by trusted
   Python whatever the model does.
3. External-system and file adapters under `connectors/`, reused by handlers.

A skill is guidance: it never enforces a permission, an approval or a write.

## Runtime and compatibility

Installed bindings live in `workflows.execution_binding`, apart from editable
`config_values`. A launch resolves the installed definition and merges run
defaults, tenant defaults and the run's own values
(`workflows.resolve_run_config`), then validates them against the run schema.
Configuration grants nothing: what a run may read or write comes from trusted
application state. The run pins its handler, definition version, bundle digest
and mirror versions before any item is queued.

Apply every pending migration with `db/migrate.py` before starting a new revision
(see [database upgrades](../db/README.md)). Stop the workers while changing
revisions, and reconcile outstanding writes first.

## Testing a new definition

Write expected outcomes outside the skill bundle, then test registration,
launch, tool answers, the server's checks, review and recovery. Cover
cross-tenant inputs, changed inputs, request replay and every consequential
write receipt. Sessions are scripted with `platform/tests/fake_agents.py`, which
calls the real tools, so the tests exercise everything after the model.

```sh
TEST_DATABASE_URL=postgresql:///postgres AUTH_DEV_MODE=1 uv run --all-packages pytest platform/tests apps/solution-api/tests connectors/tests db/tests -q
npm --prefix apps/solution-web test
npm --prefix apps/solution-web run build
npm --prefix apps/solution-web run lint
npm --prefix apps/windows-app test
npm --prefix apps/windows-app run build
```

Set `TEST_DATABASE_URL` to a PostgreSQL role that can create databases. Pytest
creates, migrates, seeds and drops a disposable database of its own; see
[isolated integration tests](../db/README.md#isolated-integration-tests).
