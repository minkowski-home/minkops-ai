# Canonical hosted skill-driven workflow architecture

## Selected architecture and scope

Skills, prompts, declared supporting resources, and adequate authorized
MCP/REST tools drive the OpenAI-managed Codex harness. Minkops owns the product
experience and thin shared controls for access, run lifecycle, approvals,
recovery, and verified results. This is the canonical architecture for new
workflow development as of 2026-10-04.

The implementation on `platform/skill-driven-workflows` includes shared
control/lifecycle boundaries and complete definition-driven hosted execution
bundles, integrated with current staging's corporate website and SMTP delivery.
Commit `6cad769` is historical evaluation evidence; there is no requirement to
maintain its branch or preserve a parallel execution methodology. Business
regression cases remain valuable regardless of implementation.

OpenAI-hosted Agents API execution and gpt-6-luna remain selected. Existing
Accounts prompts, business checks, Excel mechanics, HTTP routes, and browser
write receipts remain the behavioral reference. The current refactor does not
enable skill-generated workbook replacements, new MCP integrations, a local
terminal executor, computer use, or generic replacement database tables.

## Reusable boundaries

- `platform/run_controls`: request identity and transactional task/event/outbox
  observations; callers retain transaction ownership and tenant authorization.
- `platform/runtime/lifecycle`: worker locking, state reload after locking,
  session/turn persistence, raw proposals before schema validation, cleanup,
  and no automatic replay of ambiguous session creation.
- `platform/runtime/bundles` and `workflow`: explicit, digest-checked execution
  snapshots and complete skill archives from repository-owned definitions.
- `platform/accounts/run_store`: existing Accounts table access behind the small
  lifecycle protocol. Catalog, approval, evidence, and write handling remain
  Accounts domain concerns.

The managed harness chooses and executes tools. There is no new application
agent loop or workflow-planning engine. Supporting skill scripts are packaged
when explicitly declared, rather than requiring another platform module.
Business-system tool access still needs real, tenant-authorized bindings;
metadata and skill instructions cannot grant access.

## Regression and evaluation gates

Run both backend suites with TEST_DATABASE_URL pointing to an isolated migrated,
demo-seeded database. The API suite mutates demo fixtures; do not use a customer
database. The setup commands are in accounts-desk.md and db/README.md.

```sh
uv run --all-packages python -m unittest discover -s platform/tests -v
uv run --all-packages python -m unittest discover -s apps/solution-api/tests -v
```

The benchmark passed 19 platform and 32 API tests with no skips before the
refactor. The same regression cases remain required; tests added for this
refactor cover bundle revision drift, complete helper/schema packaging,
manifest metadata, resource escape, definition identity, durable launch
snapshots, replay, actual database locks, raw rejected proposals, cleanup, and
legacy queued-run behavior. The OpenAPI document must remain identical to the
benchmark. Source prompt hashes remain checked by package-boundary tests.

| Business guarantee | Existing evaluation reference |
| --- | --- |
| Ambiguous routing is reviewable and cannot commit | API/Excel routing and discovery tests |
| Duplicate invoices and explicit edits behave correctly | Excel duplicate and unique-key tests; API repeat-bill journey |
| Formulas, unrelated sheets, adjacent tables, and styles survive | Real openpyxl adapter tests |
| Changed files, interrupted receipts, and cancelled saves remain honest | API cancellation/receipt tests; browser local-commit tests |
| Inputs, destinations, settings, and audit records stay tenant-scoped | Auth, Accounts API, workflow configuration tests |
| Worker retries do not blindly repeat paid execution | Shared lifecycle tests and hosted saved-turn tests |

For the later working-copy pilot, evaluate the same outcomes independently of
which code created the workbook. Add representative customer-approved samples
and record extraction accuracy, correction/review effort, latency, API cost,
preservation failures, and recovery outcomes. Keep expected answers outside
agent bundles. A matching file hash or agent self-verification alone does not
establish semantic correctness. No economic improvement is claimed by this
structural refactor.

The completed refactor passed 35 platform and 36 API tests with no skips, plus
10 frontend tests, TypeScript/Vite build, and lint. OpenAPI and the original turn
instruction hashes matched the benchmark. A real hosted API smoke test found
row-2 headers and extracted a ₹24 invoice into the intended workbook. Its prior
formula and unrelated sheet survived; a temporary file read-back receipt
completed the task, and both hosted sessions were cleaned up. This was API and
local file verification, not a new browser directory-grant or deployment check.

## Rollout and recovery

No migration is required: execution snapshots use the existing run config JSONB.
Drain old queued work before switching workers. An old queued run without a
complete bundle requires explicit relaunch, while a saved active session uses
its existing turn and artifact path without new input. Discovery catalogs and
approved writes retain their existing validation and receipt semantics.

Do not run two worker revisions as a rollout strategy for changing workflow
instructions. Current refactor prompts match the benchmark, but the older
worker does not honor the new complete bundle. Select one revision, preserve
run/session records, and reconcile outstanding writes before rolling back.
Local testing is separate from production deployment.
