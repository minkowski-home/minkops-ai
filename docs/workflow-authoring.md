# Authoring and installing workflows

Workflows use repository-owned skills and the managed hosted runtime. Minkops
owns authorized inputs, durable runs, human review, independent checks, and
verified writes. Start with an existing handler and tools; introduce custom
Python only for a demonstrated gap or a guarantee the application must enforce.

## Repository contracts

```text
employees/<employee>/
  employee.json
  workflows/<workflow>/
    workflow.json
    SKILL.md
    execution-instructions.md
    tenant-config.schema.json
    run-config.schema.json
    output.schema.json
    agent-output.schema.json       # optional separate proposal contract
    scripts/                      # explicitly bundled helpers, if needed
solutions/<client>/
  solution.ts                     # existing console branding/composition
  installation.json
  employees/<employee>/binding.json
```

`employee.json` defines `key`, `name`, `description`, `config_schema`, and
`defaults`. See `employees/accounts-desk/employee.json` for the installed example.
An employee is a product grouping, not another agent execution loop.

`workflow.json` declares the owner, version, skill/schema paths, tenant/run
defaults, and hosted execution settings. Three additional fields select reuse:

- `handler`: `skill.proposal`, `accounts.discovery`, or `accounts.bill`.
- `presentation`: `proposal`, `accounts-discovery`, or `accounts-bill`.
- `capabilities`: required authorized capabilities; currently `files.snapshot`.

Workflow identity and handler identity are separate. Several definitions can
reuse a handler with different procedures and valid configuration. Tenant keys
must be unique. Use Accounts handlers only for their actual catalog/bill
contracts; their specialized UI includes existing native discovery behavior.

The default `skill.proposal` handler accepts authorized existing file snapshots,
validates the declared output schema, waits for review, and records a completed
result after approval. It does not perform external writes. Its product adapter
renders primitive schema fields, file selection, and result review. Complex
resource selection or business review requires a product adapter. No new default
workflow or employee is installed by this refactor.

Skills require YAML `name` and `description`. List every supporting script or
reference in `execution.resources`; undeclared files, credentials, and expected
evaluation answers must never enter the bundle. Hosted Python helpers can be
ordinary Python scripts. Network access is disabled for the current runtime;
declaring a capability or connector does not enable a business-system MCP/API.

## Client composition and installation

`solutions/<client>/installation.json` selects an **existing** tenant and enabled
employee references. For example, the current mock composition is:

```json
{"tenant": "mock-tenant", "employees": ["accounts-desk"]}
```

Each selected employee has a client `binding.json` containing `workflows`:

```json
{
  "workflows": [
    {"key": "bill-entry", "status": "active",
     "defaults": {"review_mode": "all_outputs", "output_mode": "excel_in_place", "input_format": "mixed"}}
  ]
}
```

First apply migrations, then validate and install through the existing uv stack:

```sh
uv run --all-packages python db/migrate.py
uv run --all-packages python -m minkops_api.install_workflows mock-client --validate-only
uv run --all-packages python -m minkops_api.install_workflows mock-client --actor-email admin@example.com --dry-run
uv run --all-packages python -m minkops_api.install_workflows mock-client --actor-email admin@example.com
```

Installation is a server administrative operation using `DATABASE_URL`.
`--actor-email` selects an existing verified tenant/platform administrator for
authorization and audit; it is not a browser authentication mechanism. Run the
CLI only with controlled administrative database credentials. The service is
independent of CLI parsing so a future authenticated admin UI can call it.

Validation checks ownership, paths, schemas, defaults, handlers, and policies.
Dry run also checks current tenant state and rolls back its entire transaction.
Installation does not create tenants/users, grant file/device access, or provision
connections. It preserves existing operator settings and employee/workflow
statuses, rejects incompatible schemas atomically, and increments configuration
versions only for schema changes. Binding status/defaults initialize new rows.
Removing a reference does not delete tenant history or disable existing installs;
pause a workflow through current settings when withdrawing it.

The web build discovers `solutions/*/solution.ts` automatically. A new client
manifest needs a rebuild, not a shared app registry edit. Tenant membership and
API authorization remain the authority for access.
If the public solution ID differs from the tenant slug, set `tenantSlug` in its
`solution.ts` manifest to match `installation.json`; no app-level alias is needed.

## Trusted Python extensions

Use three extension locations:

1. Workflow helpers under `employees/`, bundled explicitly for model execution.
2. Application handlers and deterministic policies under `platform/`, run by
   trusted Python independently of model compliance.
3. External-system/file adapters under `connectors/`, reused by handlers.

Handlers are ordinary Python objects. The explicit registry is
`platform/src/minkops_platform/runtime/handlers.py`; never import a Python module
named by a customer request. A handler implements `prepare_launch`, `prepare`,
`validate`, and `finish`; specialized review implements `approve`. `prepare`
returns files, model context, and domain context. `validate` checks the proposal;
`finish` decides review/completion using the shared store. The shared lifecycle
owns locking, session recovery, raw-result persistence, and cleanup. A new
handler should not recreate those controls or an agent planning loop.

`prepare_launch` returns `runtime.launch.LaunchInputs`: authorized files, input
IDs, optional catalog ID, validated selections, and optional server-owned domain
snapshots. Snapshots cannot override runtime/selection fields. Clients cannot
submit snapshot fields. A handler may implement `launched(connection, run)` to
create durable domain children inside the launch transaction. Bill Entry uses
this for independent paid sessions under one parent review task; the shared
store excludes aggregate parents from execution and children do not update the
parent task directly. Accounts remains an adapter over this single runtime.

Client destination restrictions in `solutions/<id>/workflow-policy.json` are
applied by declarative installation to the registered schema. Mock-client keeps
Bill Entry Tally-only; the reusable workflow retains its Excel/Tally choices.
Run snapshots and deterministic threshold policies survive batch aggregation,
review, retries, and later installation changes. Explicit approval is required
before preparing Tally writes, which independently enforce pinned review policy.

An existing workflow can select a client policy in its trusted binding:

```json
{"key": "review-threshold", "config": {"field": "Amount", "amount": 50000}}
```

Place that object in the workflow item's `policies` array. The dormant reference
policy requires explicit review above the threshold, rejects missing/invalid
amounts, and runs again before preparing writes. It is exercised in tests and
is **not enabled** for either current client. Run preferences cannot override it;
existing runs retain their launch-time policy after installation changes.

When adding another policy, register its schema and deterministic Python function
in `platform/src/minkops_platform/workflow_policies.py`. Client files select and
configure trusted implementations. Never treat a skill helper as enforcement of
a mandatory client rule. For a consequential destination, enforce authorization,
approval, idempotency, and independent destination readback in the adapter path.

## Runtime and compatibility

Installed bindings live in `workflows.execution_binding`, separate from editable
`config_values`. Launch resolves the installed definition, checks adapter-owned
resources, and pins handler, policy, authorized resource IDs/hashes, the complete
skill bundle, and definition version before queuing. Reserved runtime fields
cannot be supplied as run configuration. New sessions use those snapshots.
Unsupported capability requirements fail before any paid execution.

`workflow_runs` owns the existing durable rows. The updatable `account_runs` view
preserves Accounts/native contracts and existing foreign-key relationships;
there is one run store and one hosted lifecycle. Existing HTTP routes remain
compatible. `accounts_worker` is the existing bootstrap command over the shared
dispatcher. Historical runs without handler bindings use the narrowly bounded
legacy Accounts mapping; legacy unpinned queued runs still require relaunch.

Apply every pending migration through `0011_complete_branch_convergence` before
starting this revision. See [branch convergence](branch-convergence.md). Stop
workers while changing application revisions, preserve session/write records,
and reconcile outstanding writes. An application rollback can use the retained
Accounts view, but never run an older Accounts-only worker against new non-Accounts
definitions. Do not drop/reverse the migration to recover an application revision.

## Testing a new definition

Write expected outcomes outside skill bundles, then test registration, launch,
schema/business checks, review, and recovery. Test cross-tenant resources,
changed inputs, request replay, and any consequential write receipt. The current
architecture tests create renamed/default definitions in temporary directories
and remove them; no test employee/workflow remains in the product.

```sh
uv run --all-packages python -m unittest discover -s platform/tests -v
uv run --all-packages python -m unittest discover -s apps/solution-api/tests -v
```

Set `TEST_DATABASE_URL` to an isolated migrated, demo-seeded database. These
tests mutate fixtures. The native and web test/build commands remain documented
in their existing guides. New business-system MCP bindings, scheduling, admin
workflow creation UI, and customer-machine Python execution are separate work.

Database-backed pytest runs now create and clean up their own database; see
[isolated integration tests](../db/README.md#isolated-integration-tests). The
supplied PostgreSQL role needs database-creation permission.
