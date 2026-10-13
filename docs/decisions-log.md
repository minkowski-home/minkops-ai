# Decision Logs

## Measure the hold rate with a labelled holdout and a free replay (13 October 2026)

**Situation:** The main complaint was too many held bills, and several releases
had changed prompts and lifecycle code without a measured end-to-end run. A
held bill could be the model's fault, the pipeline's, the provider's or a
correct exception, and every paid rerun to tell them apart cost money.

**Task:** Measure Bill Entry 0.12 on realistic documents, separate model errors
from pipeline errors, and fix what the measurement shows without trading holds
for silent accounting errors.

**Action:** Built one tool on two existing seams. `replay` feeds a run the
answers a correct agent returns through the worker's executor parameter, so
validation, master selection, aggregation, attention and the companion's
read-first Tally save run on real PDFs without a model. `score` grades each
input against a labelled package and treats wrong saves, missed exceptions and
double saves as critical. A dry replay of 36 labelled bills passed 36/36 before
any paid run. The paid gpt-6-luna run of 39 bills (36 labelled plus a
two-invoice PDF with an e-way bill, a quotation and an off-day date) then
isolated each remaining failure. Two were provider errors: a dropped stream now
reattaches to the existing turn, while an ambiguous session creation stays an
explicit Recheck. Three were instruction gaps, fixed as general rules: supplier
identity must come from printed identity, not purpose or history (a bill
printing only a shared leading name had been saved to one of two suppliers);
the split-tax capability is named by its exact path; and a scanned GSTIN that
fails its check character is re-read as a misread, not treated as a conflict.
Exercising the one-click decisions live surfaced four product bugs, each fixed
test first: Do nothing on a non-bill made every later approval fail, stopping a
batch duplicated every bill in Attention, a busy run answered decisions with a
permission error, and a re-held bill stayed marked Done.

**Result:** 31 of 36 labelled bills passed on the first paid pass (two provider
errors, two unnecessary holds, one missed exception). Every other saved voucher
matched the ground truth on company, supplier, ledger, date, amounts and each
tax line; the edge cases passed 3/3. After the fixes and
targeted reruns all 36 reach their expected outcome, including Create this
ledger, an in-place correction and Recheck after provider failures. A free
rerun of all 36 created no voucher. One bill saved before the supplier rule
remains in the test company under the more plausible supplier.

## Version delivered context so pinned runs keep their exact bytes (13 October 2026)

**Situation:** After one 39-bill batch, a discovery refresh of three small test
companies exceeded the 8 MB hosted context budget and was marked partial, which
blocks confirmation and therefore Bill Entry. About half of each native voucher
record's bytes were empty tags. Every launched run pins the SHA-256 of each
context file, and execution refuses inputs that differ from that snapshot.

**Task:** Shrink the delivered context without discarding evidence, breaking
record offsets used by the master index and cited notes, or failing runs
launched before the change.

**Action:** Added a versioned compact record format. New discovery catalogs are
stamped with it; delivery then drops empty strings, nulls and empty containers
but keeps every list position and meaningful values such as 0 and "No".
Unstamped catalogs keep the previous serialization, so earlier pinned hashes
still match. The stored native export is unchanged.

**Result:** The measured package fell from 8.35 MB to 4.78 MB and the refresh
was complete and reused its confirmation. This doubles headroom, not unbounded
scale: larger customers will need per-bill context retrieval rather than full
history delivery.

## Trace a misleading Tally rejection to company settings (13 October 2026)

**Situation:** Two clean, correctly extracted March bills failed natively with
"Voucher date is missing". The message was first mistaken for a Tally restart,
then for an unknown date-setting problem. Each attempt consumed a review decision.

**Task:** Find the real cause and stop the bill before an import attempt,
without ever changing a source date to make Tally accept it.

**Action:** Comparing the native company exports showed two of the three
companies' books begin on 1 April 2026, so Tally refuses March vouchers. The
companion already fetched every company field during discovery, so no
desktop release was needed. Bill targets now carry the books-beginning date
from the discovered identity. Validation holds an earlier bill with a coded
"Before books begin" reason through the same path used before approval and
again before dispatch. Snapshots without the field skip the check.

**Result:** Unit and database tests hold a pre-books bill before any write
intent, with a specific Attention label. Older pinned runs are unaffected.

## Enforce what may block a bill in the model's output schema (13 October 2026)

**Situation:** Under Only exceptions, any free-text finding held a bill. Local
runs held routine bills for "arithmetic reconciles", "optional cost code absent"
and speculative duplicate warnings that misquoted invoice references. Three
releases of prompt wording reduced but could not eliminate this, because prose
cannot enforce severity.

**Task:** Make routine observations structurally unable to block a supported
bill, without hiding genuine uncertainty or weakening deterministic checks.

**Action:** Bill Entry 0.12.0 replaces findings with typed exceptions drawn from
a closed list of ten genuine blockers, plus non-blocking notes. Possible
duplicates have no code; native reconciliation decides them. One adapter maps
exceptions to the existing internal blocking findings plus codes, so storage,
review, batch aggregation and older pinned runs are unchanged. Attention labels
now come from codes instead of keyword guesses. Bills held under exception-only
authorization are flagged in shared Attention, which they previously were not.

**Result:** Schema tests reject free-text findings and unlisted codes. A
database regression shows a bill carrying the former noise saving automatically
while its sibling's uncertain ledger holds with a "Ledger unclear" Attention
item. A live run is still required to measure the model's adherence.

## Separate destination holds from interpretation holds (13 October 2026)

**Situation:** When Tally refused a supported bill (for example its date
settings), the run returned to review with only Best guess write available,
although the companion's message pointed to a Resume saves button that was not
shown. Retrying through Best guess write opened a human-review item for what was
a technical failure.

**Task:** Give destination failures a one-click recovery that repeats the
authorized plan without creating review work or bypassing checks.

**Action:** Holds caused by the destination now carry a `save_hold` reason. Those
are native refusals, unavailable PCs and reservation conflicts; interpretation
uncertainty never sets it. Retry save, limited to the run's operator, clears
only those holds and re-sends the proposal through normal approval. It relies on
the native save's read-first idempotency: an equal voucher is skipped and a
different one becomes a correction. The UI derives buttons from one tested view
function, and the server refuses Best guess write for a held save.

**Result:** Database regressions prove a rejected save is retried with the same
plan and Tally ID, and completes without a review item. A PC-unavailable hold
reports 409 while the PC is offline and completes after the same installation
reconnects.

## Derive bill completion from record outcomes, not the clearing action (13 October 2026)

**Situation:** A Tally bill saved through Best guess write could stay listed as
unresolved forever. The decision cleared a copied list, but approval rebuilt the
result from the stored proposal, so run completion still saw the issue. Batch
re-aggregation also re-read each child's original output when a sibling was
rechecked, restoring issues the operator had already decided. A saved bill shows
no buttons, so the run could only be stopped.

**Task:** Make run state follow verified outcomes, keep operator decisions
authoritative across rechecks, and preserve the separate best-guess review.

**Action:** Add one invariant, applied wherever results are finalized: an input
is unresolved only while some proposal for it is still pending or held. A held
save stays visible, and Recheck bill stays available. After the first
aggregation, only the rechecked input adopts its child's new output; every other
input keeps the parent's decided state.

**Result:** Database regressions cover a single run and a batch recheck with a
saved and with a held sibling. The saved bill completes the run while its
best-guess review stays pending in Attention.

## Contain one batch's failure inside the shared worker (13 October 2026)

**Situation:** An attention audit review found that batch aggregation ran every
tenant's bill batches in one transaction with no error handling. A Tally batch
whose destination PC was revoked raised `ServiceError` from job enqueueing, which
was not a `ValueError`. It escaped to the worker lanes, stopped the process, and
repeated on every restart. Hosted runs for all tenants stalled with it.

**Task:** Make one tenant's defect unable to stop others, and turn the known
cause into a truthful, recoverable bill outcome without weakening authorization.

**Action:** Each parent now aggregates inside its own savepoint. Unexpected errors
are rolled back to that savepoint, recorded as internal diagnostics, retried for
a bounded three ticks, then fail that run visibly with an attention item.
Background dispatch to an offline PC holds the bill with a `save_hold` reason for
an explicit retry. An operator's own approval still gets the immediate
"Reconnect this PC" error. Database tests then showed the diagnostic itself was
missing: the parent's `FOR UPDATE` lock blocked the separate diagnostics
transaction's foreign-key check. Switching to `FOR NO KEY UPDATE`, the pattern
already used by `run_for`, still serializes aggregators.

**Result:** Regression tests prove a revoked PC holds clean bills instead of
raising. They also prove an injected defect in one batch leaves another batch
writing, and fails only the broken run after three attempts with its diagnostic
and attention item.

## Keep display projections outside discovery confirmation fingerprints (11 October 2026)

**Situation:** Database integration tests found that confirming discovery saved
UI-derived master summaries into the native catalog. An identical refresh then
appeared changed, requested review again and dropped confirmed context notes.

**Task:** Preserve truthful count displays while making confirmation and unchanged
refresh operate exclusively on native evidence and approved interpretation.

**Action:** Confirm from a copy of the stored catalog instead of the presentation
projection; apply approved mappings explicitly. Extend the database regression to
compare native sources before/after confirmation while checking the response still
contains display summaries. Verify unchanged refresh, notes and archive behavior
against an isolated PostgreSQL instance using the existing test-database lifecycle.

**Result:** Presentation metadata cannot contaminate persisted source fingerprints;
unchanged discovery retains confirmation and evidenced notes. The full suite passes
259 tests and 49 subtests against disposable PostgreSQL, with no skipped tests.

## Separate native discovery evidence from indexed master lookups (11 October 2026)

**Situation:** Two test companies displayed 198/195 masters. Read-only native
comparison proved the counts included statutory definitions, an identical
currency repeated by Tally, and a remote-company metadata trailer.

**Task:** Make counts and downstream lookup truthful without losing source
evidence, merging company identities, or changing already-authorized inputs.

**Action:** Preserve native catalogs and archives; derive versioned company-scoped
master files and type/GUID/name indexes with candidate locations and raw record
provenance. Collapse only identical definitions, reject conflicting native
identities, and verify metadata against the owning company. Keep statutory,
custom and GST tax-unit masters. Pin the derived format at collection/launch;
historical runs retain exact file contents and hashes. Display unique per-type
counts separately from native export totals and update versioned workflow guidance.

**Result:** Regression coverage verifies identity conflicts, name collisions,
cross-company isolation, chunk locations, provenance and immutable legacy inputs.
The supplied real export produces 196/193 unique masters while retaining all
useful definitions; the seven derived input files total about 3.2 MB.

Entries below preserve historical decisions and may describe structures that
have since changed. See `engineering-architecture.md` for the current model.

### 2026-09-29 — Shared tenant app and clean OLTP baseline

**Situation:** The old first-boot schema, dbt warehouse, and Airflow stack no
longer fit the approved product model. The customer console still used mock
agents and teams.

**Decision:** Start a new versioned PostgreSQL OLTP schema for verified users,
tenant membership, employees, workflows, task observations, and an event
outbox. Keep the warehouse empty for separate design. Use declarative JSON
Schema settings and tenant-admin or platform-admin editing. Leave agent
execution and event publishing for later work.

**Action:** Remove the old database and warehouse implementation, add a clean
migration and mock-tenant fixture, confine image-to-Excel to that fixture,
and move the shared console to real tenant data. PR Infra starts empty. Four
brand themes are available in the same app for every tenant.

### 2026-09-29 — Employee-owned workflows and a self-hosted Agents API environment

**Status:** The self-hosted environment choice was superseded by the
2026-10-01 OpenAI-hosted Accounts implementation. The 2026-10-02 clarification
below confirms hosted execution for the current refactor. Employee/workflow
ownership and the managed-harness boundary remain applicable.

**Situation:** The workflow-first layout did not mirror the customer-facing
Employee → Workflows model. It also assumed Minkops would implement much of
the agent execution logic, while the product direction is to use the Agents
API's managed Codex harness and available tools, skills, plugins, web search,
and MCP connections as much as practical. Minkops wants to run its own
execution environments, potentially on GCP.

**Decision:** Put canonical workflow definitions under
`employees/<employee-id>/workflows/<workflow-id>/` and customer-specific
composition under `solutions/<client-id>/employees/<employee-id>/`. OpenAI
manages the harness and session orchestration; Minkops manages isolated
self-hosted executor environments, product policy, and verified outcomes.
Write custom connectors or functions only for concrete integration gaps.

**Action:** Replace the empty top-level `workflows/` scaffold with `employees/`
guidance and update current architecture, solution, platform, connector, and
infrastructure guidance. Retain the working apps, warehouse, and solution
manifests. No Agents API integration or cloud deployment is claimed by this
directory change.
### 2026-10-03 — Keep website inquiry delivery inside the repository layers

**Situation:** The corporate website's discovery form needed real server-side
delivery, while its API package ships independently from the broader backend.
Embedding SMTP construction and retry policy in the HTTP app would couple
transport details to the external provider and make the delivery behavior hard
to exercise separately.

**Decision:** Keep request validation, CORS, HTTP errors, and request rate
limiting in `apps/corporate-website/api`. Put the submission value, bounded
best-effort duplicate control, and delivery orchestration in `platform/`; keep
Workspace SMTP configuration, MIME construction, and network calls in
`connectors/`. Package only these scoped modules into the standalone website
container rather than importing unrelated platform features.

SMTP does not offer an idempotency key for this flow. The process-local guard
suppresses identical submissions while its state exists and records an
uncertain result after an ambiguous send failure. This is not durable or
cross-instance exactly-once delivery; visitors are told not to resubmit when
acceptance cannot be confirmed.

**Result:** API, orchestration, and transport behavior can be tested at their
respective boundaries, and the website release does not need unrelated
Accounts, authentication, or database packages.

**Follow-up:** Production preflight exposed that the relay rejected the default
localhost SMTP greeting before authentication. The connector now identifies
itself with the verified public domain and distinguishes connection/TLS/auth
failures from uncertain failures after message submission begins. Logs keep
only the failure phase, exception class, numeric response code, and a safe
reason category. The no-message production preflight authenticated, and the
received test message's raw headers showed only the public sender/return path;
SPF, DKIM, and DMARC passed. No private mailbox identity is recorded here.

### 2026-09-28 — Workflow-first Python architecture and lean repository layout

**Situation:** The repository's backend architecture centered named agents, a
generic agent runtime, and a capability layer, while the product direction
centers preset business workflows. The dbt warehouse also lived under an
ambiguous catch-all `modules/` directory.

**Decision:** Treat workflows as the primary execution unit. AI Employees are
product catalog groupings only. Keep one-off model instructions with their
workflow; extract reusable skills only after another workflow needs them. Use
agents only for autonomous reasoning loops inside workflows. Tools are
concrete operations, and connectors provide external-system implementations.
Do not add a capabilities layer without a concrete substitution, discovery,
or permission need.

**Action:** Remove the obsolete `platform/ai/` agent and runtime trees. Move
the dbt project to the root-level `warehouse/` directory, update its compose mount, and refresh
current architecture guidance. Shared reusable Python workflows belong under
`workflows/`; one-caller workflow code can remain with its application or
solution until reuse justifies extraction.

**Result:** Current repository guidance follows the workflow-first model and
does not present the retired agent runtime as Minkops' Python execution
architecture. Earlier entries below record historical decisions.

### 2026-09-21 — Starter workspace before client-specific UI

`apps/solution-web/src/starter` owns the default operator workspace: the
activity list, action queue, and agent context are useful core anatomy before a
solution has bespoke screens. A solution may optionally supply
`solutions/<solution-id>/web/src/App.tsx` when its reviewed workflow requires a
different interaction model. PR Infra inherits the starter workspace while its
WhatsApp-to-Excel workflow, rules, schemas, and connector implementations are
still being developed; mock-client demonstrates manifest configuration without
claiming ownership of the shared console. Shared elements remain explicitly
owned by `apps/`, `platform/`, `modules/`, `connectors/`, or `packages/`.

### 2026-09-22 — One public console for every solution

`app.minkops.com` is a shared Minkops host, so choosing a solution at Vite build
time would require a deployment per client and would make client routing depend
on infrastructure. The console now includes a small runtime manifest registry
and scopes every screen under `/<solution-id>/...`; both `pr-infra` and the
`mock-client` fixture use the same built app. Authentication will replace this
explicit URL selection with tenant membership before production use. The Vercel
SPA rewrite is co-located with `apps/solution-web`, while project creation and
domain attachment remain a deployment operation rather than solution code.

### 2026-09-21 — Solution composition boundary for multi-client delivery

**Situation:** The repository grouped active code by implementation category (`agents`, `services`, `shared`, and `transform`), while a single customer console was beginning to receive a substantial UI redesign. Extending that shape for different customer interfaces, connectors, and workflows would invite copied applications and customer rules scattered through shared code.

**Task:** Preserve the working product while making the customer boundary explicit without prematurely inventing empty services or a migration system that does not exist.

**Action:** We moved the deployable console/API to `apps/solution-web` and `apps/solution-api`; the reusable AI decision library and runtime to `platform/ai`; and the dbt reporting project to `modules/reporting/warehouse`. Brand code moved to the intentional `packages/brand` package. We retained `db/init` because it is mounted by Docker as first-boot DDL, not an incremental migration mechanism. Most importantly, `packages/solution-contracts` defines the compact, typed composition contract and `solutions/example/ui.ts` provides a non-customer fixture. The console selects a solution from `VITE_SOLUTION`, letting a solution control its product label, navigation, enabled connector declarations, and UI options while retaining one shared application binary.

**Result:** Future customer work has an unambiguous home (`solutions/<id>`), integration code stays isolated in `connectors/`, and shared capability work is visible as platform or module work. The refactor keeps current imports and local compose paths valid while preventing customer-specific copies of the web and API apps.

### 03-02-2026
We created `docs/decisions-log.md` as the canonical place to store product briefs (new launches), onboarding playbooks, system design decisions, problems found and how they were fixed, architecture notes, and governance policies. When new cross-cutting decisions are made — for example, conventions for knowledge graphs, audit trails, or policy enforcement, or any major improvement/trade-off — we capture them in `docs/` so every module (apps, services, infra) can reference the same playbook, similar to a monorepo “engineering handbook”. There isn’t a strict schema beyond including the date; entries should be explanatory paragraphs that a junior engineer can use to understand senior trade-offs.


### 2026-02-04 
We consolidated duplicated agent-facing schema definitions (e.g., `Ticket`, `KBChunk`, `TenantProfile`) into a single, typing-only module at `agents/src/agents/shared/schemas.py`. Previously, identical concepts were redefined across `agents.shared.db`, `agents.shared.kb`, and the Imel agent’s `state.py`, which introduced drift (for example, `keywords` was typed as a string in one location and a list in another) and forced downstream code to use `typing.cast` to bridge mismatched types. We explicitly avoided importing these types from `agents.shared.db` or `agents.shared.kb` into agent state modules because those helpers carry heavier runtime dependencies (database drivers and optional KB/LLM dependencies), and coupling state definitions to them increases the chance of import-time failures in minimal environments and creates an undesirable layering inversion. Centralizing shared schemas in a pure-typing module keeps imports lightweight, prevents schema drift, and allows persistence/KB helpers and agent state to share a stable contract without circular dependencies or runtime coupling. As part of the change, we also added small normalization helpers in the KB loader to coerce potentially user-authored metadata into the canonical schema types.

### 2026-02-05
We removed `services/orchestrator` to eliminate a naming collision with the previously planned “Airflow orchestrator” (scheduler/manager) concept and to keep the repository’s layering unambiguous while the system is still small. `services/ai-suite` is now the single agent runtime orchestrator: it executes agent graphs from `agents/`, owns all operational side effects (Postgres reads/writes, outbox emission, inter-agent messaging, and external actions), and provides capability implementations grouped by domain rather than by agent. The `agents/` package remains a decisioning library plus contracts; agent `tools.py` files define Protocol-based capability requirements (verbs), `schemas.py` defines shared data shapes (nouns), and `state.py` defines per-run in-memory state, with concrete implementations living exclusively in the service layer. This capability-first runtime layout is intended to scale to many agents without per-agent infrastructure modules, while keeping the system explainable in interviews: “agents decide; the runtime executes and persists; shared capabilities are implemented once and reused everywhere.”

### 2026-02-06
We generalized the runtime execution contract so it no longer assumes every agent is email-centric. The previous `run_agent_once(...)` implementation had Imel-specific arguments (`email_id`, `sender_email`, `email_content`) and Imel-specific post-run behavior (send draft response email), which would not scale to heterogeneous agents. To fix this, we introduced an adapter layer (`services/ai-suite/ai_suite/runtime/adapters.py`) where each agent defines three concerns: payload validation/normalization, mapping payload into graph runner kwargs, and post-run effect handling. The core runner now accepts a generic `input_payload` dictionary and delegates agent-specific behavior to the adapter selected in the registry. This keeps the runtime stable as new agents are added and avoids centralizing agent-specific `if/else` logic in orchestration code. We also added a minimal but functional Kall agent path (`agents/general/kall`) that loads a ticket, resolves it, updates ticket status, and sends an inter-agent completion message, wired through the same generic runtime contract and CLI (`run-agent` plus `run-kall` convenience command). This preserves strict separation of concerns while proving that multiple agents with different trigger semantics can coexist without changing directory structure or rewriting core orchestrator flow.

### 2026-02-06 (LangGraph Standardization)
We upgraded both Imel and Kall to execute through compiled LangGraph workflows as the primary runtime path, instead of manual Python control flow. `run_imel(...)` and `run_kall(...)` now build their respective graphs and call `graph.invoke(...)`, while still exposing simple service-facing entrypoints for `ai-suite`. This keeps node logic unchanged and portable, but moves orchestration semantics (node graph, edges, `Command(goto=...)` routing, and thread execution config) into LangGraph where they belong. We also propagated the orchestrator `run_id` into agent runtime kwargs and use it as LangGraph `thread_id`, so runtime run records and graph execution traces share the same correlation key. This design gives us production-ready graph execution today while preserving the adapter/registry architecture for heterogeneous agents and future capabilities like durable checkpoints, resume/replay, and graph-level observability.

### 2026-02-08
We hardened local runtime bootstrap to handle realistic developer environments where the Postgres role can create databases but cannot create the `vector` extension. Previously, `seed-db` failed early at `CREATE EXTENSION vector`, which blocked tenant provisioning and then caused follow-on runtime failures (`runs.tenant_id` foreign key violations) because the tenant seed step never ran. We changed `db/init_agents_db.sql` to attempt extension creation with an explicit fallback path and to create `tenant_kb_chunks` with either a `vector` column (preferred) or a `JSONB` embedding fallback when pgvector is unavailable. We also updated the seeding code to detect which column shape exists and insert accordingly, preserving a single CLI flow without requiring superuser privileges in local development while keeping the production path vector-native.

During the same recovery pass we fixed two additional boot blockers discovered while validating the full CLI flow end-to-end. First, `seed-db` defaults (`db/init_agents_db.sql` and `data/...`) were relative to repository root but often executed from `services/ai-suite`; we added deterministic path resolution so defaults now work from either location. Second, the schema used `messages.current_role`, which is a problematic reserved identifier in this context; we replaced it with `messages.role` so database creation is stable. After unblocking bootstrap, `run-imel` surfaced a separate runtime issue where `_classify_email` and `_draft_reply` were referenced but undefined; we restored these helper paths with robust deterministic fallbacks and guarded LLM parsing, so the graph now executes both without `--use-llm` and with model responses. The validated result is a successful sequence of `seed-db`, `run-imel`, and `run-kall` in local shell execution.

### 2026-02-26
We split `db/init_agents_db.sql` into two files: `db/bootstrap.sql` and `db/schema.sql`. The original file conflated two distinct concerns — cluster-level one-time setup (creating the database, installing extensions, configuring roles and grants) with the repeatable schema DDL (table definitions, indexes, seed rows). This meant that any manual role or grant setup was silently lost every time `seed-db` was run, because the DROP/CREATE DATABASE cycle wiped everything inside the database and there was nowhere durable to re-apply the grants.

`db/bootstrap.sql` is now the one-time admin script, run as the `gauss` OS superuser against the `postgres` maintenance database. It idempotently creates the `minkops` application role (login-only, least-privilege), creates `minkops_app` if it does not exist, installs extensions (`uuid-ossp` and `vector` with the existing privilege-fallback guard), grants `minkops` connect access and schema usage, and sets `ALTER DEFAULT PRIVILEGES` so that every table `gauss` creates in the future automatically gets `SELECT/INSERT/UPDATE/DELETE` for `minkops` — without requiring a re-grant after each schema reset. `db/schema.sql` now contains only the teardown (`DROP TABLE IF EXISTS` in reverse FK order) and rebuild (all `CREATE TABLE`, indexes, and seed rows), assumes the database already exists, and connects directly to `minkops_app` with no `\c` meta-command. `seed_database()` in `seed.py` was updated to drop the `_admin_url()` helper (which previously re-pointed psql at `/postgres` to avoid a "connected to the database you're dropping" error) and instead pass `database_url` directly to psql, since the schema reset no longer touches the database itself. The `--sql-path` default in `cli.py` was updated from `db/init_agents_db.sql` to `db/schema.sql`.

- There needs to be an alert system when status of a side effect in `event_outbox` goes `dead`. Currently, dead events just sit there until someone queries.

### 2026-02-27
Fixed two bugs in `db/additional_metrics.sql`. First, `make_interval(hours => ...)` was receiving a `bigint` — `ROW_NUMBER()` returns `bigint`, promoting the whole `(slot * 2 + tenant_ord) % 24` expression, and PostgreSQL has no implicit `bigint → int` narrowing in named-argument calls; fixed with an explicit `::int` cast. Second, the lead funnel events `INSERT ... SELECT` referenced a `pr` alias throughout but had no `FROM picked_run pr` clause — the CTE was defined but never bound into the final SELECT.

### 2026-02-28
Hardened `human_instructions_queue` into a proper pull-based work queue to support safe concurrent agent workers. Added scheduling and leasing fields (`available_at`, `locked_at`, `locked_by`, `lease_expires_at`) enabling the standard `FOR UPDATE SKIP LOCKED` claim pattern — without these a multi-worker deployment would process the same instruction twice or get stuck on dead leases. Added retry/backoff fields (`attempts`, `max_attempts`, `last_error`) mirroring the contract already established in `event_outbox`; `max_attempts` defaults to 3 rather than the outbox's 10 because human-authored tasks should surface failures quickly rather than silently retry. Added routing separation (`assigned_agent_id`, `assigned_by`, `assigned_at`) alongside the existing `target_agent_id`/`target_role` — "target" preserves human intent while "assigned" records the planner's runtime decision, which matters once load balancing and reassignment are in play. Added `result_payload JSONB` for structured outputs (dashboard and downstream automation need more than a text blob), `idempotency_key` with a partial unique index (same pattern as `event_outbox`) to prevent duplicate agendas from UI retries, and `failed`/`dead` to the status CHECK constraint so the worker has explicit, queryable terminal states rather than encoding them implicitly in `attempts + last_error`. Renamed `run_id` to `last_run_id` to accurately reflect that retries can spawn multiple runs and this column always holds the most recent one. Indexes were restructured to include `available_at` in all worker-facing queries and a dedicated partial index on `lease_expires_at` for the dead-lease reclaim sweep. Agent→human interrupts remain in `agent_intercom_queue` (`kind='question'|'signal'`, `channel='human_interrupts'`) — mixing them into this table would conflate two lanes with different SLA models, ack contracts, and consumers.

### Database Design
#### `tenant_id` doesn't reference the tenants table

  This is a deliberate architectural choice, not an oversight. The outbox is infrastructure — it's a durable delivery mechanism that needs to function even in degraded states. If tenant_id had a foreign key to tenants, then deleting or disabling a tenant would either cascade-delete pending outbox events (losing in-flight work) or block the tenant deletion entirely due to the constraint. Neither is acceptable behavior for an outbox.
  More broadly, the outbox is append-only operational infrastructure. It doesn't need referential integrity to tenants to do its job — the tenant_id there is purely for partitioning and filtering work by tenant, not for enforcing relational correctness. The same reasoning applies to activity_logs, which your schema comments already acknowledge explicitly.

### 2026-03-14 — Monorepo-wide brand token system and client-app frontend

We introduced `shared/brand/` as the single source of truth for all design tokens across Minkops apps. The problem it solves: `apps/corporate-website` had fonts hard-coded in its own `index.css`, and `apps/client-app` was starting from scratch — with two apps and more planned, per-app colour constants would drift immediately.

The mechanism: `shared/brand/tokens.css` declares all CSS custom properties (`--color-*`, `--glass-*`, `--shadow-*`, etc.) under `:root` and `[data-theme="..."]` attribute selectors. Each app's Vite config defines an `@minkops/brand` path alias pointing at `../../shared/brand` (depth-adjusted per app). Each app's `index.css` begins with `@import "@minkops/brand/tokens.css"`. Adding a new app requires adding two lines — one alias, one import — and zero copying. Vite resolves CSS `@import` aliases through the same transform pipeline as JS, so no separate tooling is needed.

Theme switching is handled in `ThemeContext.tsx`: setting `document.documentElement.setAttribute("data-theme", theme)` causes the entire CSS variable set to swap instantly via the cascade — no JavaScript iterates over DOM nodes or applies inline styles. The attribute is applied to `<html>` (not a subtree) so it cascades into portals and modals rendered outside the React root. The choice persists to `localStorage` with a safe try/catch guard for private-browsing environments.

The `apps/client-app` frontend was scaffolded as a production-grade Vite + React + TypeScript app. Domain types in `src/types/` were written to describe the shape of data the backend will return — backend engineers can treat these as an informal API contract before the OpenAPI spec is written. Mock data in `src/mock/` mirrors these shapes exactly, so UI development is completely decoupled from backend availability.

The dashboard layout uses CSS Grid at two levels: AppShell splits the viewport into a sidebar column and a main area; the main area splits into a fixed header row and a three-column content row (agents 288px | chat 1fr | interrupts 320px). Pane content is passed as render props (`leftPane`, `centerPane`, `rightPane`) so AppShell is a pure layout host — panels have no knowledge of each other or the shell, making them independently testable and replaceable.

### 2026-03-18 - Removing the `bootstrap.sql`
The error is precise and the cause is clear. bootstrap.sql uses psql-specific variable substitution syntax — :'minkops_password' — which is a psql client meta-feature, not standard SQL. When Docker's entrypoint executes init scripts, it runs them directly against the database using its own internal mechanism, not through a psql session with -v flags. The variable is never defined, so the syntax fails immediately.
This is actually a deeper design conflict: bootstrap.sql was written to be run manually as a one-time setup command with psql postgres -v minkops_password=$MINKOPS_DB_PASSWORD -f db/bootstrap.sql. It was never designed to be a Docker init script, and it should not be one. Everything it does — creating a role, creating the database, installing extensions, granting privileges — is already handled by Docker's Postgres entrypoint via the POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB environment variables you have defined.
The fix is to remove bootstrap.sql from the init scripts entirely and only mount schema.sql. Change your db/init/ directory to contain only schema.sql (or rename the mounted file to 01_schema.sql), and remove 01_bootstrap.sql from it. The Compose environment block already handles everything bootstrap was doing.

### 2026-03-27 — Multi-step questionnaire funnel with dynamic agent recommendation

**Situation:** The corporate website landing page had no mechanism to guide prospective customers toward the right Minkops agent. Visitors could browse the agent roster but had no interactive path to understanding which agents solved their specific problems, and "Request Access" was the only call-to-action regardless of the visitor's context or business scale.

**Task:** Introduce a qualification funnel embedded between the hero banner and the agent roster that collects four signals (revenue band, time-sink areas, biggest bottleneck, and weekly hours), then surfaces a personalised Minkops agent recommendation with a conservative hours-recovered estimate.

**Action:** Built `QuestionnaireFunnel.tsx` as a self-contained, four-step interactive component. Key design decisions:

1. **Priority resolution algorithm**: The "biggest bottleneck" answer (step 3) maps directly to a primary agent key via a static `PRIORITY_MAP`. The multi-select time-sink answers (step 2) power the secondary agent recommendations. If a step-3 answer is absent or ambiguous, the fallback is the first selected time-sink key — this covers edge cases where the user skips or backtracks, without requiring server-side scoring logic.

2. **Theme-token compliance**: Zero hardcoded colour or font values in the component. All styles reference CSS custom properties from `shared/brand/tokens.css` (`--color-primary`, `--font-heading`, `--glass-bg-heavy`, etc.), so the funnel inherits light, dark, and paper themes automatically without a line of JavaScript.

3. **AnimatePresence with mode="wait"**: Framer Motion's `AnimatePresence` wraps each step with `mode="wait"` so the exit animation of the outgoing step completes before the enter animation of the incoming step begins. This prevents layout overlap during fast clicks — a subtle but meaningful production-quality detail.

4. **Accessible ARIA semantics**: Each option button carries `role="radio"` or `role="checkbox"` (determined by `question.type`) and `aria-checked`, making the funnel keyboard-navigable and screen-reader-friendly without a third-party form library.

5. **Minkops agent name fidelity**: Agent recommendations display canonical agent names (Kall, Leed, Imel, Eko, Floc, Insi) from `agentDirectory.ts` rather than generic labels — keeping the funnel results grounded in the actual product rather than hypothetical agent archetypes.

6. **Section-scoped layout**: Rather than a fullscreen takeover (the original reference used a fixed full-viewport layout), the funnel is a `<section>` that respects the existing landing page grid (`width: min(1280px, 100%)`), sits visually between the hero glass panel and the agent roster, and shares the `.glass-panel-vibrant` surface treatment used by the hero — creating visual continuity without new design language.

**Result:** Visitors get a personalised agent recommendation in under two minutes of interaction, with a concrete hours-recovered estimate that quantifies the ROI before they request access. The recommendation CTA scrolls to the existing `#access` section, so the funnel feeds directly into the existing conversion path without a new page route.
### 2026-09-18 — Corporate website rebuilt on the new design system, with honesty enforced by data

**Situation:** The marketing site (`apps/corporate-website`) still shipped the retired visual language: glass panels, animated gradient orbs, framer-motion entrances on every section, a three.js dependency, and tokens imported from `shared/brand/`. The new design system in `design/` replaced all of that with a flat, hairline-ruled system, and it made honesty rules load-bearing: only Imel and Kall are live, no invented metrics, no implied customers. The old site broke those rules in several places. One case study claimed $1.2M revenue and a 42% conversion rate from agents that don't exist yet. A roster showed no status at all, and a "demo film" placeholder advertised "< 200ms latency".

**Task:** Recreate every route on the new system with no placeholders, rewrite the copy in a warmer voice, and make it structurally hard for the site to overclaim again.

**Action:**
1. **Content as typed data, with status as a single source of truth.** Agent status lives only in `src/content/agents.ts`. The hero counts, roster tiles, funnel results and orchestration flow badges all derive from it. The orchestration page computes each flow's badge ("Eko next · Kall live", "All in build") from the roster rather than hard-coding it, so promoting an agent is a one-line change that can't leave a stale claim anywhere else. The funnel shows a non-live recommendation as "Next" and says so in words.
2. **Estimates carry their basis.** The funnel's recovery maths moved into a pure `buildResult()` with the assumption exposed as `RECOVERY_BAND`. Verifying it in the browser caught a real bug: a visitor who picked "8 to 15 hours" was told "the 15 hrs you told us about". The result now names the band they chose and the number we computed from. The old code also rendered "1–1 hrs" for the smallest band; that case now reads "about an hour".
3. **Primitives styled by class, not inline objects.** The design system ships its components with inline styles and `useState` for hover. Ported as-is, every button would carry a hover state machine, and `:hover`/`:active`/`:focus-visible` would be impossible to express. The port keeps the design-system APIs but renders BEM classes, so the "colour-only interaction" rule lives in CSS where it belongs.
4. **Decoupled from `shared/brand/`.** The client app still uses the old token set, so repointing that shared package would have restyled the console as a side effect. The site now vendors the design-system tokens (`src/styles/tokens.css`) and drops the alias. The trade-off is a copy to keep in sync, accepted because it keeps the blast radius to one app.
5. **Routing correctness.** A single `SiteLayout` with nested routes replaced per-page nav/footer duplication. A `ScrollManager` keyed on `location.key` fixes cross-page hash links (`/#access` from `/about`), which BrowserRouter never handled. The unpublished post's URL redirects to `/blogs` through a `RETIRED_POST_SLUGS` list instead of 404ing an indexed link, and a real 404 page replaced the old catch-all that silently rendered the landing page.
6. **A grid overflow bug found on mobile.** On the lead-generation post the 375px layout viewport widened to 544px. The code block was a grid item with the default `min-width: auto`, so its `white-space: pre` content stretched the track instead of scrolling. `min-width: 0` on the prose grid children fixed it. This is the classic "grid/flex child won't shrink" trap.

**Result:** 13 routes rebuilt with zero framer-motion/three.js (both removed from dependencies). The bundle is 255 KB JS / 82 KB gzipped. Every agent claim on the site now traces back to one file. The waitlist form still has no backend (documented under "Known limitations" in the app README); that is the next piece of real work.

**Follow-up, same day: designing for "no prompts" and for a roster of 100.**
Two design reviews reshaped the landing page. First, the console illustration had shown a chat thread with an agent, which is exactly the prompt box Minkops exists to remove for non-technical owners. It became a decision queue instead. Agents report finished work as plain-sentence log rows. Anything above their authority arrives as one question with two or three answers already worked out, and the recommended answer is marked. The operator's entire interaction is one click, after which the agent picks the work back up and the result lands in the log. One implementation detail: the first version drove the "agent is working" delay from a `useEffect` over the chosen set. That re-armed every in-flight timer whenever state changed, so choosing a second answer restarted the first one's countdown. The timers now start at click time and live in a ref, cleared on reset and unmount.
Second, the roster was a flat grid of 11 cards, and at 100 agents that becomes a wall. It now has three layers: a status bar that summarises any roster size in one line; department filters, the grouping that stays meaningful as the roster grows; and a windowed grid showing two rows at a time. The column count is measured from the live CSS grid with a `ResizeObserver` rather than assumed from breakpoints, so a "batch" is always exactly two full rows at any viewport, with a four-card floor on phones. Newly revealed cards fade in with a 40ms stagger, and live agents always sort first. Items are keyed by filter plus name so that switching departments replays the entrance; keying the whole list instead would have remounted the `<ul>` and left the observer watching a detached node.

**Follow-up: one roster, four businesses, no status tiers.** Per product direction the site no longer splits agents into live / next / in-build. The status field, its sort order and every derived badge were removed. The roster now carries a department and a present-tense "right now" line per agent, plus a shift strip that stays compact at any team size. Three roles were added for new verticals (Sito, site coordinator; Tali, bookkeeper; Rota, staffing coordinator), with glyphs drawn on the existing head-and-shoulders motif. The console illustration became a framed app window with four switchable workflows: Shopify store ops, construction site-to-books (WhatsApp messages and photos to Tally/Excel to dashboards and invoices), staffing (sick calls, cover, UKG), and social content. The data lives in `content/consoleWorkflows.ts`. State is kept per workflow and decision timers are keyed by workflow plus decision, so a decision started on one tab still completes after you switch away, and switching back shows it resolved. The tab list follows the WAI-ARIA tabs pattern (roving tabindex, arrow/Home/End keys). On mobile it becomes a horizontal strip that keeps the active tab in view by adjusting the strip's own `scrollLeft`, because `scrollIntoView` would also scroll the page.

### 2026-10-01 — Agent-selected Excel destinations with a verified local commit boundary

**Situation:** Clients have different workbook layouts, header positions and
business schemas. A fixed invoice template would constrain the product; a
hosted agent overwriting local files would bypass user authority and invite
stale writes or duplicate entries after a lost connection.

**Task:** Ship discover → confirm → extract → review → in-place save while using
the OpenAI-managed Codex harness and keeping multi-tenant controls maintainable.

**Action:** Moved execution to per-run OpenAI-hosted environments with gpt-6-luna.
Codex recognizes actual files, sheets and named tables; user-confirmed mappings
create the business contract. Ambiguous destination recognition blocks commits.
Pinned instructions, result schema, input hashes and catalogs make runs auditable.
A database worker saves session IDs incrementally and reconciles existing turns
without blind replay. Composite tenant keys, request idempotency and workbook
reservations guard concurrent operations. The deterministic adapter preserves
unrelated cells and rejects table expansion into occupied content. The browser
retains granted directory handles, checks source hashes, writes approved bytes,
reads them back and submits a verified receipt. Already-applied bytes resume
without another append; cancelled saves retain their audit and accept honest
late receipts. Hosted environments are cleaned after durable results.

**Result:** The real mock-client journey discovered row-4 headers and processed
three PDFs plus a scanned image. Four reviewed records appended to the existing
local register (16 → 20 rows), with prior rows and reference workbooks preserved.
The task completed only after the browser's matching receipt. Regression tests
also cover schema/routing ambiguity, adjacent tables, formula preservation,
duplicate rejection, tenant isolation and interrupted write recovery. A real
sample exposed optional workbook protection metadata being absent; a failing
regression test led to handling that valid Excel case without weakening protected
workbook checks. This is local verification, not a production deployment claim.


### 2026-10-01 — Restore application and connector boundaries without changing workflow behaviour

**Situation:** Accounts workflow commands, hosted session calls, workbook mechanics
and HTTP routes had accumulated in the solution API. The worker even imported
write preparation from the web layer, making reuse depend on the deployment app.

**Task:** Restore the repository's intended ownership while preserving the
existing workflow, public API, worker command and local-write safeguards.

**Action:** Extracted Accounts services, persistence, checks and worker execution
into `platform/`, Excel mechanics into `connectors/`, and model turn instructions
into the employee workflow assets. HTTP authentication, CSRF, multipart parsing
and error responses remain in the API. Small compatibility imports preserve old
callers; workspace dependencies declare the direction explicitly. No new service,
queue, plugin framework or deployment boundary was introduced. Added a one-line
ownership rule to `AGENTS.md` and regression tests for boundaries and legacy storage.

**Result:** All 32 API and 19 platform tests pass. The Accounts OpenAPI contract
matches the pre-refactor snapshot exactly, and extracted model instructions match
the original hashes. Shared services import with both the API package and FastAPI
blocked. Excel tests retain destination selection, edits, formula preservation,
duplicate checks and write receipts. Running workflow processes were left alone;
this verifies the code refactor rather than claiming a new deployment.

### 2026-10-02 — Hosted execution and skill-first refactor scope

**Situation:** An architecture review proposed self-hosted execution and broad
Accounts generalization, despite the selected OpenAI-hosted implementation.
This mixed a future local execution method with the current hosting decision.

**Task:** Clarify the architectural boundary before implementation so the
refactor maximizes managed Codex capabilities without rebuilding available
execution features or introducing an unrequested customer-device runtime.

**Decision:** Retain OpenAI-hosted Agents API environments. Keep all four
README workflow methods in mind, prioritizing adequate REST/MCP integrations
and skill-driven execution. Customer-machine terminal execution and computer
use remain outside the current refactor. Most product development belongs in
apps; employee skills own procedures, and platform remains a thin shared layer
for concrete permissions, lifecycle, approvals, recovery, and verification.
Add deterministic code only for demonstrated gaps or enforceable guarantees.

**Action:** Reconcile the README, architecture, infrastructure, and historical
decision status. Separate current behavior from planned evaluation/lifecycle
refactoring and a later hosted working-copy pilot.

**Result:** Documentation now states the selected hosting decision and each
method's scope explicitly. No runtime implementation or deployment change is
claimed; improvements to workflow economics remain to be evaluated.

### 2026-10-02 — Pin complete skill revisions behind reusable hosted run controls

**Status:** The 2026-10-04 decision below makes this architecture canonical and
ends the requirement to retain a separate benchmark methodology. Results and
commit references in this entry remain historical verification evidence.

**Situation:** Accounts pinned SKILL.md and its proposal schema at launch, but
loaded turn instructions from the current checkout during execution. A queued
run could therefore execute a different revision from its recorded definition.
Worker locking, session persistence, cleanup, launch identity, and task/outbox
observations were also coupled to the first employee's implementation.

**Task:** Make hosted workflow execution reproducible and reusable without
rebuilding the managed harness, changing customer-facing writes, or introducing
a self-hosted executor or speculative database framework.

**Action:** Add an explicit hosted execution descriptor to each workflow. Pin a
digest-checked bundle containing instructions, schemas, declared resources,
model, packages, and output path before queueing. Package the complete skill
from that snapshot and support additional helpers without directory scans.
Extract shared request/observation controls and worker lifecycle behavior behind
a small Accounts persistence adapter. Retain domain checks, approvals, and
verified browser writes. Reject unpinned legacy queued runs explicitly while
reconciling saved sessions without replay. A live provider call rejected product
copy used as skill metadata; a failing regression test led to deriving name and
description from the pinned YAML manifest using a standard parser.

**Result:** The benchmark branch remains at 6cad769. The refactor passes all 35
platform and 36 API tests with no skips, plus 10 frontend tests, TypeScript/Vite
build, lint, and an unchanged OpenAPI contract. Source prompt hashes match the
benchmark. A bounded real hosted API journey discovered row-2 headers, extracted
a ₹24 invoice, preserved an existing formula and unrelated worksheet, and
completed after a temporary local file was reread and its receipt submitted.
Both hosted sessions were released. This verifies the API/runtime/file-receipt
path locally; it does not claim a new browser directory-grant check, production
deployment, improved workflow economics, or the later workbook-editing pilot.

### 2026-10-03 — Define the Employee/Workflow model and make discovery delivery explicit

**Situation:** The corporate site mixed a fictional employee roster, unsourced time-saved estimates, and simulated external actions with product descriptions. Its discovery form validated locally but did not deliver visitor submissions.

**Task:** Make the product structure legible across the existing site and deliver submitted discovery details to the fixed Minkops inbox without reporting provider acceptance as inbox receipt.

**Action:** Reframed supporting copy around an AI Employee as the product grouping and a Workflow as a defined outcome, procedure and review path. Removed the roster and obsolete live handoff diagrams; replaced the savings calculator with an illustrative outline and labeled the retained console scenarios as fictional. Wired the existing form to a FastAPI endpoint that validates fields, caps the request body, rate-limits before schema validation, ignores a honeypot, and sends escaped text/HTML through Google Workspace SMTP to info@minkops.com. The recipient, public From identity and subject are server-controlled, the visitor email is Reply-To, and SMTP credentials stay in Secret Manager. Because SMTP has no provider idempotency key, a deterministic Message-ID and bounded process-local duplicate guard suppress accepted and ambiguous retries without claiming durable exactly-once delivery. The browser reports success only after the SMTP server accepts the message.

**Result:** The API suite covers delivery, fixed target and sender, field validation, duplicate/ambiguous outcomes, SMTP failures, request escaping, missing configuration, rate limiting and CORS; the frontend passes its production build and lint. Real SMTP acceptance, deployment configuration, sender-alias header privacy and recipient inbox receipt remain unverified until a controlled deployment and send. SMTP acceptance is intentionally not presented as proof of inbox delivery.

### 2026-10-04 — Adopt the skill-driven architecture and reconcile current staging

**Situation:** The hosted workflow refactor and subsequent corporate-site/SMTP
work had diverged from the same Accounts implementation. Keeping an obsolete
benchmark methodology alive was no longer aligned with the selected product
direction, while replacing the staging snapshot would discard recent work.

**Task:** Integrate both histories safely and make skill-driven Codex execution
with authorized MCP/REST capabilities the canonical architecture for future
workflow development.

**Decision:** OpenAI-hosted Agents API owns the harness and AI execution loop.
Employee skills, prompts, and supporting resources own workflow procedure.
Existing adequate tools and integrations are preferred; custom implementation
serves demonstrated gaps or enforceable controls. Minkops owns the product
experience and thin shared permissions, lifecycle, approval, recovery, and
verification boundaries. The old methodology remains history, with no separate
branch or parallel-maintenance requirement. Business regression checks and
necessary deterministic adapters remain applicable.

**Action:** Merge origin/staging at af95d82 into platform/skill-driven-workflows
without rewriting either history. Preserve both decision-log additions and the
merged SMTP/YAML dependencies, and update README, architecture guidance, the
implementation guide, and AGENTS.md. Keep corporate website, SMTP delivery,
and design source files identical to staging. Main and staging refs are unchanged.

**Result:** The combined backend suites pass 93 tests and 27 subtests with no
skips using an isolated migrated/seeded PostgreSQL database. All 10 solution-web
tests pass; both frontends pass TypeScript/Vite builds and lint. The dependency
lock validates with uv sync --locked, and Git reports no whitespace errors.
These are local integration checks; no new live model call, SMTP message,
production deployment, or PR merge is claimed.

### 2026-10-05 — Share the desktop product and separate local execution authority

**Situation:** MIN-117 needed a Windows product capable of reaching local Tally
and files, with web parity and future cross-device continuity. Duplicating the
UI, account database or agent loop would create drift and fragment task history.
Blindly retrying an interrupted financial write could duplicate entries.

**Task:** Add the smallest useful native companion while preserving existing
identity, approvals and verification, and make execution understandable to
nontechnical users. Scheduling and UI testing were explicitly deferred.

**Decision:** Serve one React UI in web and sandboxed Electron, with the existing
verified email/password accounts. PostgreSQL owns tasks, selected file versions
and receipts. A registered companion polls outbound HTTPS for an allowlist of
bounded operations; Windows-encrypted local state holds only necessary grants,
credentials, pending receipts and recovery backups. The OpenAI-hosted Codex
harness remains the AI execution loop; no local shell or self-hosted agent is
introduced. This also lets a future mobile client use the same durable runs.

**Action:** Put device/job controls in `platform/`, reusable worker recovery in
`platform/desktop-runtime`, native Tally/filesystem adapters in `connectors/`,
and IPC/HTTP transport in `apps/`. Scope credentials to account/workspace and
recheck membership and source ownership. Persist every request key, including
requests joining an existing job. Automatically reclaim only read jobs; recover
saves through explicit requests, native before/after hashes, encrypted backups,
atomic replacement and existing Accounts byte verification. Late cancellation
receipts record applied writes without changing the cancelled run to success.
Native save events report waiting, saving and attention states; only the domain
can complete a multi-workbook run. Shared progress uses observed business stages
and actual counts, with evidence/activity expandable instead of simulated ETAs.

**Result:** The full backend suite passes 111 tests and 27 subtests on a freshly
migrated/seeded isolated PostgreSQL database. All 15 web and 13 native tests pass;
native file tests also pass on Windows, including junction containment. A real
HTTP/PostgreSQL/Windows smoke verifies folder refresh, lost-acknowledgement
recovery and device revocation. A headless Windows Electron check confirms
credential encryption. The x64 NSIS installer builds natively and its packaged
bundles match the compiled source without unbundled workspace dependencies.
The app's new dependency audit is clean. WSL packaging limitations were resolved
with a Windows-local compiled build directory; the working repository and
backend environment remain intact. Live Tally reads are unverified because the
local service is stopped; the unavailable path is verified. The installer is
unsigned, deployment is separate, and MIN-121/122 retain scheduling and UI/clean
Windows 10/11 install checks as Todo. No paid model call or accounting write was
made for this verification.

### 2026-10-05 — Verify the live Tally XML contract before closing the desktop work

**Situation:** Restarting Tally exposed a real response shape absent from the
original fixtures: `<NAME TYPE="String">` becomes an object when XML attributes
are preserved. The connection check reported `[object Object]` as a company name
instead of the actual text, despite the service responding successfully.

**Task:** Correct the native adapter and prove that the actual company name
survives the full Windows-companion/API/task-result path.

**Action:** Add a failing regression for typed names and attribute-only names,
then explicitly extract scalar text or the typed element's `#text`. Reject
unexpected nested name structures instead of string coercion. Add an optional
expected-company assertion to the HTTP smoke, including durable task status and
queued/executing/completed events. Rebuild the Windows installer with the fix.

**Result:** Live read-only company export returns `Minkops Test`; the real
Windows/HTTP/PostgreSQL journey persists that name and completes its task.
Folder refresh, interrupted receipt recovery and revocation still pass. All 14
native tests pass on Windows and Linux; the full backend regression suite passes
111 tests and 27 subtests. No accounting write was made. UI and clean-install
checks remain the separately deferred MIN-122 work.

### 2026-10-05 — Make source discovery portable without moving the agent onto the client

**Situation:** The next Bill Entry workflows need real Tally and Excel structure
from a client's PC. A server cannot read that PC's loopback Tally service or
private folders, while machine-specific paths and a second agent loop would
break web/desktop parity and future cross-device continuity.

**Task:** Build a configurable mock-client discovery MVP on MIN-117, with
server-owned catalogs, explicit initial review, stable refreshes and observable
partial results. Keep the default broad enough for Bill Entry and preserve the
existing hosted business-mapping and financial-write contracts.

**Action:** Add one bounded native collection operation, scoped to registered
devices, explicit folder grants and fixed read-only Tally collections. Keep
filesystem/XML adapters in connectors, durable orchestration in platform, and
transport/UI in apps. Observe tables, shifted headers, typed reference values,
formulas and nested Tally tax settings; validate workbook hashes and coverage
against server bytes. Reuse the existing hosted mapping skill and task lifecycle
rather than introduce a local agent. Store versioned JSON catalogs and offer an
explicit download, with no automatic local copy. Fingerprint structural changes
independently of ordinary Excel rows, remap approved mappings to current file
versions, and require review when structure or reference mappings change.
Incomplete catalogs retain successful observations but cannot be confirmed or
used by dependent workflows. Partial scans avoid paid mapping; progress reports
each source/category and renews bounded read claims. Rejected receipts become
visible failures rather than endless reclaim loops.

**Result:** The full backend suite passes 119 tests and 27 subtests; 20 native
tests pass on Windows and Linux, and all 15 web tests, build and lint pass.
Live Windows/API/PostgreSQL tests collect the actual Minkops Test company and
all 11 configured reference categories, read a synthetic Excel workbook, run
the real hosted mapping skill, confirm its three tables, retain confirmation
on unchanged refresh, and recover from unavailable Tally and damaged workbook
partial results. The 0.2.0 installer bundles these adapters; customer PCs need
no repository, WSL or developer runtimes. A separate local demo database and
shared UI support the meeting. One hosted sandbox setup failed; explicit retry
succeeded, and the failed run retained its catalog. Cleanup of that failed
session was still rejected by the provider; background retries are spaced and
capped without falsely marking it closed. Visual and clean Windows 10/11 checks
remain MIN-122 Todo, including packaged launch blocked by automatic review.
Production deployment and scheduling remain separate.

### 2026-10-05 — Preserve Excel discovery after approved workbook writes

**Situation:** An additional interoperability test appended a dummy bill and
expanded its named table using openpyxl, the application's approved writer.
Native discovery then failed because ExcelJS 4.4 cannot resolve valid
package-absolute table relationship targets (upstream issue 1468). Ordinary
fixtures generated by ExcelJS did not reveal the failure.

**Task:** Make the native reader compatible with our existing writer without
dropping named tables, changing original bytes or requiring Python on clients.

**Action:** First add a failing regression using absolute table targets. Resolve
those internal relationship URIs to equivalent relative URIs in a bounded,
in-memory ZIP copy before ExcelJS reads it. Preserve original bytes for hashes,
uploads and approvals. Add JSZip as an explicit dependency; keep external
relationships untouched. Invalid relationship XML is rejected. Verify identical
table/header/value observations and unchanged input bytes, then repeat the real
Windows discovery/confirmation/partial/recovery journey with the openpyxl-saved
workbook.

**Result:** Both native test suites and the real API refresh pass, including
retained confirmation after the added bill row and expanded table. Discovery
continues to expose named tables and the approved write contract uses the
original workbook bytes.

### 2026-10-07 — Separate installed workflow composition from durable execution

**Situation:** Versioned skill bundles and hosted recovery were reusable, but
employee registration lived in demo seeding and launch/worker/UI dispatch depended
on two Accounts workflow names. Adding clients or procedures risked modifying
shared execution code or weakening deterministic write guarantees.

**Task:** Refactor the same app from Windows branch `c3b050c` into a repeatable
installation and execution path, preserving current discovery, review, Excel
writes, native receipts and recovery. Retain ordinary Python extension points
without adding another employee or business workflow.

**Action:** Introduce validated employee/client definitions and an atomic
installation service/CLI with a genuine transactionally rolled-back dry run.
Separate trusted execution bindings from editable settings. Pin handler, policy,
resource IDs/hashes and complete skill bundles at launch. Dispatch ordinary
Python handlers through the existing hosted lifecycle; keep Accounts business
validation and write mechanics in its domain. Promote the existing run table to
`workflow_runs`, preserve IDs/FKs and provide an updatable Accounts compatibility
view. Extract shared resource lookup and run observations, add explicit client
policy registration, and enforce review policies before writes independently of
model behavior. Discover client manifests at build time and select existing
product adapters from installed presentation metadata. Use isolated temporary
definitions to test different identities/default execution without installing a
second product workflow. Document authoring, extensions and rollout/recovery.

**Result:** The isolated full Python suite passes 139 tests and 31 subtests;
17 web and 20 native tests, web build/lint, native build, and changed-Python lint
pass. Actual hosted discovery and bill extraction read a synthetic invoice for
24, proceed through review and saved-byte verification, preserve a formula and
an unrelated sheet, and clean up their sessions. Windows HTTP/native smoke
verifies folder refresh, receipt replay after worker recreation, device revocation,
and successful live Tally connection after Tally is started. Edge desktop/mobile
checks cover current launch screens, a verified task, settings persistence,
activity expansion and four themes with no runtime errors or horizontal overflow.
Client threshold tests block auto-write, permit explicit approval and retain the
run's policy after tenant changes. Existing separator encoding artifacts remain
baseline UI debt. No production deployment, new business-system MCP integration,
new employee/workflow, or later Bill entry/Tally financial-write branch changes
are included. Future real workflows still need business-specific evaluations.
### 2026-10-06 — Separate bill identity and approved intent from task execution

**Situation:** MIN-119 needed parallel scanned-bill extraction on the existing
Windows/web app. Replayed tasks, backfills and corrections could otherwise
duplicate accounting records, and one unreadable bill could block an entire batch.

**Task:** Keep source accuracy authoritative across hosted sessions, human review,
registered-PC execution and restarts, while preserving platform/connector/app
boundaries and the shared UI.

**Action:** Use durable per-input hosted sessions under one review task, with
independent failure handling and bounded worker concurrency. Derive bill identity
from supplier/invoice/financial year or confirmed Excel business keys; reserve
approved writes independently of task IDs. Scope Tally reservations by observed
company GUID across PCs. Persist immutable approval plans and queue native jobs
in the same transaction. Reconcile existing destination data before writing;
hold different versions for explicit edits, compare extraction/read snapshots,
and require exact saved-byte or ledger readback. Late cancelled Excel receipts
retain audit evidence without replacing newer source metadata. Persist rejected
inputs on batch children so sibling retries cannot resurrect old failures.

**Result:** Parallel worker, duplicate/correction, partial failure, cross-PC
reservation, stale review, cancellation and receipt regressions pass against
PostgreSQL. Real gpt-6-luna sessions extracted complex raster bills into both
Tally and inferred Excel contracts. Windows native saves and replayed receipts
verified destination data; a provider-interrupted blank input was retried without
repeating three successful sibling writes. Visual/installation QA stays MIN-122.

### 2026-10-06 — Catch a Tally correction that silently became a creation

**Situation:** Live testing of a synthetic Purchase correction showed that a
MASTER ID selector without its original DATE could create another voucher,
despite an apparent import success. Tally also assigned its own company GUID
suffix instead of retaining the requested UUID on creation.

**Task:** Prevent acknowledgements from masquerading as correct accounting data
and implement an observed-identity correction contract.

**Action:** Require the original DATE and MASTER ID for Alter, explicitly reject
a CREATED response during correction, and re-export matching vouchers after
every save. Verify a unique business identity, exact approved date and signed
ledger amounts, and unchanged observed GUID during update. Add a failing native
regression for the incorrect selector, then repeat the real Windows/Tally test.
Remove only the duplicate synthetic test voucher after identifying its master ID.
Guard complex existing inventory/bill/payment/cost allocations so the fixed mock
Purchase contract cannot flatten financial structure it does not represent.

**Result:** Live create, exact replay, correction handoff, approved Alter and
unique readback pass. Protocol failures, ambiguous keys, changed fingerprints,
wrong readbacks and unsupported allocations cannot be reported as saved.

### 2026-10-06 — Keep client policy trusted while preserving reusable workflows

**Situation:** The mock-client RC must save only to Tally, while the shared
workflows retain Excel/Tally/Both choices and future client rules remain unknown.
Editable preferences alone would let a caller bypass a disabled UI option.

**Task:** Enforce the client restriction without embedding mock-client routing
throughout the API, shared workflow or native adapters.

**Action:** Bind repository-owned solution policy into the registered JSON Schema,
retain the visible enum and annotate enabled choices. Validate settings and launch
destinations against trusted registration. Preserve other clients' definitions
when no policy exists and keep each run's versioned execution snapshot immutable.

**Result:** Schema, authenticated launch and preference-override regressions pass;
mock-client can save only to Tally. Source discovery remains independently
configurable, and later client rules have an explicit composition boundary.

### 2026-10-06 — Preserve financial approvals across periodic discovery

**Situation:** A live bill approval was blocked by an unchanged periodic discovery
even though its confirmed catalog and company identity were identical. Supplier
remediation also needs newer masters without replaying already verified bills.

**Task:** Allow safe refreshes while retaining immutable approvals, exact source
identity and per-bill recovery.

**Action:** Add failing database regressions, then accept an older pinned catalog
only when the newer catalog is ready and its fingerprint is identical. For a
supplier clarification, rebind only that retry to a confirmed catalog on the same
PC/company GUID. Keep saved/duplicate siblings intact. Fix retry progress and
review counts to exclude already checked bills, with regression coverage.

**Result:** The installed app saves the remediated hire bill after a periodic
refresh. A second five-input batch skips every duplicate after an independent
reference clarification. Worker restart retains paid session identities, and
original Test Company vouchers remain byte-equivalent after normalization.

### 2026-10-06 — Make catalog export reliable in the installed Windows shell

**Situation:** Visual RC testing found that Chromium's catalog download returned
HTTP success but left an incomplete temporary file rather than the requested
OneDrive artifact.

**Task:** Produce a complete user-selected catalog without exposing arbitrary
filesystem writes or renderer-controlled network requests.

**Action:** Add bounded native IPC for an authenticated tenant/discovery ID, fetch
the fixed authorized endpoint, show Save As and delegate file writing to the
connector. Validate JSON extension, size and regular-file/parent containment;
sync a temporary file and replace atomically. Add failure/containment regressions
and verify the installed app's actual Windows picker/export.

**Result:** A complete 537,848-byte catalog is saved in OneDrive. Native regression
suites and live Windows export pass; the reusable adapter stays in connectors,
while Electron owns only authenticated transport and the native dialog.
### 2026-10-07 — Converge independently evolved workflow architecture and financial execution

**Situation:** The shared declarative-workflow refactor and the complete Bill
Entry RC had diverged from the same Windows baseline. Keeping only either tip
would discard architecture or financial behavior; a mechanical replay restored
the old Accounts-specific launch/store/worker. Both branches also published a
different `0009`: Bill Entry required a table where the architecture exposed a
compatibility view, so an architecture-first upgrade failed its foreign key.

**Task:** Retain independent paid sessions, per-bill recovery, financial approvals,
duplicate/correction/readback guarantees, native exports and client policy on one
shared runtime. Upgrade existing databases without rewriting applied checksums,
resetting history or abandoning pending financial intents. Preserve recoverable
source revisions before retiring superseded development branches.

**Action:** Replay all seven Bill Entry commits onto the architecture in a new
consolidation branch, then move domain resource preparation/checks/finish behavior
into registered Accounts handlers. Share launch identity, trusted snapshots,
session lifecycle, durable store and child observations; retain Bill Entry's
batch orchestrator and bounded native adapters. Apply client destination schema
policy through installation and independently enforce pinned review policies
before writes and after batch aggregation. Add two guarded schema bridges around
the immutable branch migrations: temporarily restore the original table name
inside the locked migration transaction, then restore the shared table/view.
Preserve table OIDs, run IDs, paid-session identities, parent links, pending plans,
company reservations, receipts and status. Test both predecessor upgrade paths,
fresh/repeated migrations and reserved-input/hash rejection before paid calls.
Archive exact original tips instead of forcing their history onto either branch.

**Result:** The combined backend passes 168 tests and 45 subtests; all 17 web
tests, production build and lint pass. Native suites pass 31 tests on Linux and
30 on Windows with one privilege-dependent symlink case covered on Linux. A
Windows-local unsigned x64 installer builds. Real hosted Excel discovery/bill
extraction and saved-byte verification preserve formulas/unrelated sheets. A
real two-bill hosted Tally batch recovers one ambiguous invoice through explicit
clarification without replaying its successful sibling, then verifies native
saves, receipt replay, duplicates and observed-identity corrections. All 10
pre-existing company vouchers remain unchanged; paid environments close.
Desktop/mobile browser checks cover both completed outcomes, all four themes and
installed client policy. The consolidated branch becomes the development home;
no merge or PR changes staging/main. Production deployment, signing and a fresh
device installation matrix remain separate.

## 2026-10-07 — Keep integration fixtures out of customer-facing workspaces

**Situation:** A local browser preview shared the database used for regression
tests. Unique simulated desktop registrations accumulated as 91 misleading
Accounts/Bill PC cards, even though only one physical PC had been connected.

**Task:** Remove the misleading registrations while retaining history, and make
the normal test path safe without relying on engineers remembering to seed a
different database.

**Action:** Before pytest collects modules, create a uniquely named database on
the supplied server, migrate and seed it, and redirect both database URLs to it.
Drop only that invocation's database at shutdown, including failures. Verify
source records remain untouched and cleanup survives an exception. Back up the
local preview database and revoke the identified synthetic registrations instead
of deleting device or financial history. Label the existing page Connected PCs.

**Result:** All 169 backend tests and 45 subtests pass in the disposable database;
the supplied database's device count remains unchanged and no temporary database
remains. Web tests, build and lint pass. The architecture and native execution
contracts remain unchanged.

## 2026-10-07 — Separate schema context from operational references

**Situation:** Discovery exported business rows and uploaded original workbooks
while its purpose was reusable schema context. Bill Entry depended on stale
catalog rows, and client-specific allocation guidance appeared in the core skill.

**Task:** Preserve tenant-specific context and verified financial writes while
making schema collection private, metadata-driven and production-compatible.

**Action:** Use bounded ODBC metadata calls and fresh header-only workbook
projections with independent server validation. Persist immutable tenant catalogs;
pin their schema in consuming runs and request live references through a separate
leased desktop job before paid execution. Refresh continuation context without
replaying successful siblings. Add validated additive employee/workflow variants,
keeping handlers and write policy core-owned. Use Firebase-compatible opaque
session cookies and prevent shared API caching. Package locked dependencies and
client definitions into a non-root deployment image; inspect cloud configuration
read-only and document worker/recovery/budget gates before launch.

**Result:** Backend, native and web regressions validate isolation, projected-byte
privacy, current-reference gating, company identity and pinned core/client context.
Current-PC ODBC metadata exposes 275 tables. Clean-PC/server-topology tests and
bounded cloud worker deployment remain explicit production acceptance gates.

## 7 October 2026 — Durable workflow wake-ups with bounded cloud execution

**Situation:** The local worker ran continuously, which would spend the small
hosting budget while idle. HTTP-triggered jobs also risk lost notifications and
duplicate paid work around transaction commits, crashes and job overlap.

**Task:** Preserve the existing workflow lifecycle and recovery while allowing
Cloud Run to scale to zero, with a single bounded processing lane.

**Action:** Add a transactional PostgreSQL generation counter, dispatch lease and
global runner lock. Commit API mutations before dispatch; acknowledge only an
observed idle generation while holding its row lock. Keep pending work on timeout
and dispatch failure, with an hourly recovery sweep. Runtime identities invoke a
fixed job through ephemeral metadata credentials. Existing per-run recovery and
native-write policies remain authoritative.

**Result:** Tests prove committed launch visibility, failed-dispatch retry,
coalescing, concurrent-runner exclusion, idle-generation races and bounded exits.
The complete backend suite passes 186 tests and 47 subtests. Deployment keeps
separate database roles and denies runtime DDL; the cloud rollout records live
verification separately from these regression results.
## Preserve real ODBC column identity during production discovery (7 October 2026)

**Situation:** The first live GCP discovery receipt was rejected even though the
Windows adapter collected 275 tables with metadata-only GetSchema calls. Tally
repeats `$Category` at positions 18 and 78 in CostCentreBreakUp and AllCostCentre;
our server assumed column names were unique.

**Task:** Preserve the provider's full schema without weakening receipt validation
or sampling business records to infer it.

**Action:** Reproduced both the valid repeated-name case and an invalid repeated
position with failing tests. Changed the validator to use ordinal column identity,
kept names/types/nullability and every existing allocation/scope limit, and tested
the real PC-to-GCP completion path rather than relying on fabricated metadata.

**Result:** Both regressions pass. The catalog retains repeated methods faithfully;
malformed receipts cannot make two columns claim the same position. The corrected
Cloud Run image accepted the real Windows receipt and its identical replay:
275 schema tables, zero business records, and a completed tenant catalog.

## Normalize typed Tally identities at the connector boundary (7 October 2026)

**Situation:** The first hosted Bill Entry run stopped before paid extraction:
Tally's XML TYPE attributes turned company GUIDs into parser objects, preventing
the workflow from pinning the observed company identity.

**Task:** Restore exact identity checks without relaxing company/ledger write
validation or exposing business data through Source Discovery.

**Action:** Added a failing native regression using real typed XML shapes and
malformed nested values. Normalize only approved operational reference fields at
the connector boundary, preserving exact strings and leading zeroes. Reject
nested records instead of stringifying or guessing identity. Publish the changed
native adapter as a new installer version rather than overwriting its predecessor.

**Result:** Typed GUID, parent and alteration identifiers pass the regression;
malformed wrappers remain unavailable. Live workflow verification is recorded
separately in the deployment checklist.

## Wake bounded workers on native context readiness (7 October 2026)

**Situation:** Review found a race hidden by slow Cloud Run cold starts: an idle
worker could acknowledge a queued bill before the PC finished its references.
Completing that job left the run queued and generated no new notification.

**Task:** Make readiness durable and immediate without polling continuously,
replaying paid work or modifying an already-applied migration.

**Action:** Added an API regression that acknowledges the initial generation,
then completes the actual native-reference protocol. A new checksum-protected
migration emits a wake when a Tally context job first becomes terminal. Its
trigger covers readiness independently of workflow-state transitions, while
identical completion replay emits no extra notification. Also added fresh-project
identity provisioning tests and idempotent creation for every runtime account.

**Result:** The previously failing readiness regression and failure-path subtest
pass; committed context is visible to the response-triggered dispatcher. The
production migration was applied with the restricted migration identity. Existing
coalescing, generation fencing and per-run locks continue to control concurrency.

## Keep operator approval guards active under optimized Python (8 October 2026)

**Situation:** Release review found that `python -O` removes assertion-based
fixture, company and unresolved-result checks from the opt-in production operator.
The server still enforces tenant/approval/write rules, but the operator could
authorize data outside its narrower reviewed release-test scope.

**Task:** Keep operator authorization independent of interpreter optimization and
prove that unsafe reviews never submit an approval request.

**Action:** Reproduced the approval submission with an optimized-interpreter
regression using an isolated HTTP transport, without touching production. Replaced
operator assertions with explicit validation errors, covered unresolved bills,
wrong companies and mismatched fixture values, and added the optimized run to CI.

**Result:** Normal and optimized checks reject unsafe reviews before `/approve`;
the valid clarification path still submits through the ordinary tenant API.
Production fixture/hash, owner and company limits no longer disappear under `-O`.

## Pin reusable client context and reconcile uncertain native imports (10 October 2026)

**Situation:** Schema-only discovery and per-bill reference exports repeated work,
missed nested client conventions and forced each run into one company. A Tally
process can exit during an import, making its acknowledgement insufficient proof
of either success or failure.

**Task:** Reuse complete discovery evidence, scan mixed-company bills before
saving, and recover native failures without introducing another accounting layer
or weakening existing approval, identity and duplicate safeguards.

**Action:** Kept core interpretation in versioned skills/configuration. Added
bounded native full-master and period-voucher exports, verified report identifiers
against primary Tally documentation, immutable local packages
and authorized hosted lookup files. Pinned company GUIDs and extraction context
per run, separated company routing from business fields, and grouped approved
plans by company. Retained the existing Purchase adapter and receipts. Shared
native recovery observes a trusted Tally process, records local diagnostics and
restarts only a disappeared instance once. Reads may retry; imports with an
unknown outcome enter read-only reconciliation and never automatic replay.

**Result:** Offline regressions exercise nested records, period and identity
validation, context pinning, mixed-company duplicate isolation, locked-company
conflicts, import acknowledgement loss and restart fencing. Desktop/mobile launch
checks show the new controls without browser errors. Existing financial recovery
checks remain in place. Installation-specific export completeness, numeric `/LOAD`
support, Windows crashes and deployment are explicitly pending in MIN-124;
offline tests do not establish live compatibility.

## Reconcile native XML representations without weakening financial guards (10 October 2026)

**Situation:** MIN-124 live testing found that Tally's detailed exports differ
from compact reference collections: message indentation creates text nodes,
DayBook appends company metadata, and numeric company/AlterID fields contain
padding and typed wrappers. Valid exports were rejected and unchanged ledgers
looked stale. A restart licence handoff also hid an import's ambiguity flag.

**Task:** Accept the installation's native representation while retaining full
evidence, company identity checks, genuine stale-master rejection and the rule
that an unknown import must never be replayed automatically.

**Action:** Reproduced each protocol failure before fixing it. Ignore only
message-level formatting whitespace; validate DayBook's ancillary company
trailer against the just-discovered GUID/name. Normalize only numeric startup
arguments and numeric AlterID comparisons, leaving original discovery records
and other identity fields intact. Preserve write uncertainty when restart or
readiness fails. Clarified versioned hosted contracts for company-scoped notes,
Excel inventory coverage and company routing outside business-field evidence.

**Result:** Regression tests reject mismatched company trailers, actual master
changes, arbitrary startup arguments and import replay. Paid gpt-6-luna discovery
and a reviewed mixed-company batch completed against real Windows Tally with
independent duplicate-free readback. Controlled termination exposed native
settings/licence handoffs, which are recorded as limitations rather than claims
of unattended recovery. Production deployment remains paused under MIN-124.

### 2026-10-10 — Decisions without accounting editors, with verifiable attention

**Situation:** Review mixed automation with editable accounting values and
correction prompts. Deferred bills could remain scattered in workflow tasks,
while accepting a low-confidence scan could be mistaken for completed review.

**Task:** Keep Minkops simple while preserving truthful automation, cross-workflow
manual obligations and auditable authorization.

**Action:** Introduce shared tenant-scoped attention events and concise one-click
decisions; reject manual accounting value edits in the API as well as removing
the UI. Keep external resolution checks read-only and pin the post-write native
fingerprint for best-guess review. Separate explicit supplier creation from reads,
verify company/master identities, then continue only the authorized bill. Preserve
ordered native writes and bounded independent hosted sessions. Consolidate the
final schema for new installs with immutable archived upgrade history for released
databases, rather than discarding checksums or paid-session state.

**Result:** Operators decide, original systems own manual corrections, and durable
attention cannot disappear merely because a workflow finished or a record was
viewed. Tests cover unchanged/changed destination evidence, wrong identities,
actor audit and independent continuation. Production remains paused.

## Preserve migration integrity during baseline readability cleanup (11 October 2026)

**Situation:** The reconciled baseline retained dump-style ALTER statements for
tables created in the same file. Folding them into CREATE statements changes the
checksum, which would block already adopted installations despite an equivalent schema.

**Task:** Improve readability without rebuilding existing databases, changing
constraint identities or weakening detection of unverified migration edits.

**Action:** Inline constraints and identities, order tables by foreign-key
dependencies, and recognize only the exact original/new baseline digest pair.
Preserve recorded history; continue rejecting unknown versions and all other
checksum changes. Extend upgrade regressions to cover original baseline adoption,
repeated migration, sequence settings and attempted unverified baseline edits.

**Result:** Fresh and legacy schemas remain equivalent, including constraints,
indexes, sequences, triggers and the updatable view. Existing rows and original
checksums survive; migration changes outside the verified pair still fail closed.

## Wait for the complete Tally startup scope before resuming (11 October 2026)

**Situation:** Live interruption testing exposed a readiness check that accepted
the first loaded company while another requested company was still loading.
A native memory-access error was also observed; its cause was not established.

**Task:** Resume only after every known numeric company identity is available,
without bypassing licence/login screens or replaying an uncertain import.

**Action:** Poll company numbers as well as listener availability and wait for
the complete observed startup scope. Add a regression that first returns one
company, then both; it fails before the correction and passes afterwards. Keep
explicit operator continuation after native handoffs separate from automatic
recovery, preserving the original plan and import count for reconciliation.

**Result:** The Windows native suite passes. Live post-import recovery reads back
the existing voucher as a duplicate with one import and one restart. Licence
handoffs remain visible; neither elapsed time nor a partial startup authorizes
a second import.

## Verify the native report honors the requested period (11 October 2026)

**Situation:** An empty-period live check exposed that TallyPrime's DayBook XML
report returned its current day despite explicit date variables. Existing range
validation correctly rejected those records, but discovery could not complete
for that period and could miss other dates inside a wider range.

**Task:** Preserve complete native voucher XML while honoring inclusive date
bounds, including empty periods and records across monthly request chunks.

**Action:** Select the native Voucher Register report, which honors the same
date variables on the installed TallyPrime. Add a failing range regression,
compare every exported master/voucher record with native XML, and exercise
populated and empty dates with nested allocations and a real custom UDF.

**Result:** Native exports preserve all records and custom fields. Empty dates
complete with zero vouchers, while date validation still rejects out-of-scope
responses. The correction is included in companion 0.6.4.

## Build Windows releases from current workspace sources (11 October 2026)

**Situation:** Native source tests passed, but an installed archive collision
check still reproduced the old behavior. Inspection of the compiled artifact
showed that npm's Windows file dependencies were copied modules, leaving the
bundle on older connector sources despite its updated application version.

**Task:** Make release builds reliably include the reviewed workspace code while
retaining the installed, locked third-party dependencies.

**Action:** Resolve both workspace packages directly to their repository entry
points in esbuild, with third-party resolution through the app's node_modules.
Verify the compiled runtime and repeat the installed archive/date-range checks.
Preserve intermediate release evidence instead of treating source tests as proof
of an installed artifact.

**Result:** The release bundle includes the range-aware voucher register, complete
company readiness and collision-preserving archive checks from current sources.
The final release is 0.6.4; earlier candidates do not establish those guarantees.

## Verify concurrency at the production entry point (11 October 2026)

**Situation:** A two-bill production run waited behind a retry, then executed its
AI scans sequentially. Local continuous-worker coverage had verified four lanes,
but the deployed bounded drain still invoked the serial primitive.

**Task:** Restore bounded independent AI execution without allowing duplicate
paid sessions, premature idle acknowledgement or unordered destination writes.

**Action:** Share the four-lane limit, replenish completed lanes independently,
and retain the runner lock until every submitted future finishes. A coordinator
alone owns wake-up acknowledgement and lease refresh. Add failing tests against
the actual drain for four simultaneous claims, slow siblings, generation changes,
overlapping runners and lane exceptions. Preserve per-run locks and saved-session
reconciliation; native financial writes retain their separate ordering controls.

**Result:** The entry-point regressions pass. Queue execution no longer depends
on whether hosting uses continuous or bounded workers. Support can verify actual
overlapping run timestamps rather than infer concurrency from source intentions.

## Preserve support evidence across business rollback (11 October 2026)

**Situation:** Runtime failures and latency investigations required streamed
cloud logs; saved outputs did not explain preparation, provider, validation or
cleanup time. A late validation failure could conceal earlier work.

**Task:** Make engineer-readable workflow evidence durable without exposing raw
provider payloads or adding detailed logs to the product experience.

**Action:** Add tenant/run-constrained internal diagnostic records with stage
timings, queue wait, file sizes, hosted event kinds and schema error paths. Use
independent short transactions with bounded connection/statement/lock timeouts.
Exclude raw provider exceptions, reasoning and credentials. Diagnostic failure
cannot commit business work early or change an already applied operation's result.
Test persistence after rollback, tenant constraints and secret exclusion.

**Result:** Engineers can reconstruct child-run timing and failure boundaries
through DB queries. Customer task events stay concise, while existing native job
errors/receipts remain available alongside the new hosted execution evidence.

## Reconcile hosted instructions with their output contract (11 October 2026)

**Situation:** A real two-bill release check matched buyer GSTINs held in modern
Tally tax-unit masters, but one otherwise truthful handoff failed validation.
Durable diagnostics identified an additional-properties schema rejection: shared
instructions still requested metadata belonging to the legacy draft envelope.

**Task:** Preserve strict output validation while removing contradictory guidance
and proving identity matching against complete native evidence.

**Action:** Explicitly distinguish legacy and hosted envelopes, retain server-owned
run metadata, and version the corrected immutable workflow. Require checking native
GST tax units before declaring buyer identifiers missing, while keeping effective
dates and unsupported tax allocations as separate findings. Verify real scanned
bills without approving unsupported financial entries.

**Result:** Schema failures are attributable through DB evidence instead of streamed
cloud logs. Prompt contracts no longer request fields forbidden by hosted validation;
logical buyer matching retains exact native destination identifiers.

## Fence discovery against company loss and retire conflicting modes (11 October 2026)

**Situation:** The latest Demo discovery completed with two companies although
Tally held a third, Pradeepraj Infra. Native diagnostics recorded a disappeared
Tally process; restart history could restore only remembered company loads. The
old settings also offered mutually exclusive depths that no longer matched the
complete client-context execution path.

**Task:** Make complete context the sole discovery contract and include configured
companies without relying on a person opening each company beforehand.

**Action:** Remove retired preferences, schemas, category selection, ODBC discovery
and reference-row extraction. Migrate installed workflow settings idempotently,
preserving historical evidence. Use Tally's native Company on Disk inventory and
live GUID/number identities to establish scope before collecting. Start a verified
local installation with numbered native company directories when stopped; load
missing companies through a graceful scoped restart. Never force-close accounting
work or replay an uncertain import. Recheck scope after restart and collection;
retain missing companies and scope changes as incomplete evidence. Keep bounded
destination-reference checks separate for already-pinned bill jobs.

**Result:** Regression tests cover company loss, additions, identity replacement,
unopened companies, stopped services, blocked closing/login and migration replay.
A live read of the Oct 1–2 period includes all three companies, with Pradeepraj
Infra's 170 masters, and reports a complete package. Production deployment and
companion rollout remain separate from this branch push.

## Measure discovery work without inventing completion (11 October 2026)

**Situation:** Discovery presented expanding record-name lists and four static
checkpoints. Large company scopes became hard to review, and a failed browser
poll could silently leave the screen frozen. Bulk Tally exports cannot truthfully
report per-ledger processing or predict hosted interpretation duration.

**Task:** Make discovery readable at scale and visibly active while preserving
immutable evidence, catalog confirmation and the product's truthful automation rule.

**Action:** Reuse server-derived master counts in searchable, paginated company
rows. Add optional bounded phase measurements along the existing connector →
desktop runtime → authenticated API path. Count verified native reads and workbook
inspections, including the final company-scope check; failed reads earn no credit.
Replace a single durable activity observation rather than adding an event per
export chunk. Keep unknown-duration work indeterminate, confirmation separate,
and source/company transitions auditable. Resume browser polling after transient
failures with capped backoff and explicit stale-state feedback.

**Result:** Regression coverage checks 13-company pagination, legacy counts,
partial results, rejected measurements, API claim fencing and unchanged completion
gates. Browser verification exercises source selection, review, reconnect recovery,
four themes, mobile layouts and reduced motion using isolated fixtures. Live Tally
and deployment verification remain separate from that UI evidence.

## Separate operator controls from execution facts (11 October 2026)

**Situation:** Workflows span hosted turns, parallel bill children, read-only native
collection and verified destination saves. Cancelling by changing a visible status
would allow stale workers to restart work, lose receipts, or repeat uncertain writes.

**Task:** Provide shared Pause/Resume and Stop controls with truthful feedback and
auditable operator intent, preserving the existing runtime and financial safeguards.

**Action:** Add one bounded task control field independent of domain run states.
Fence worker selection, approval and new browser plans; serialize hosted dispatch
and finishing against the run locks used by controls. Pause native discovery at read
boundaries while renewing its existing claim. Stop cancels unsaved intents, retains
verified and late receipts, and sends remaining business items to shared attention.
Use the existing task timeline/outbox for actor audit and wake the cloud worker on
resume, even after it acknowledged an idle queue. Unknown-duration work remains
indeterminate and a stopped task never acquires a fictional completion percentage.

**Result:** PostgreSQL integration covers concurrent duplicate actions, operator
authorization, resume wake-up, hosted work stopped before review, blocked approvals
and late Excel/Tally receipts. Native tests cover pause/resume boundaries, offline
pause retention and stop propagation. Browser checks exercise controls and verify
paused/stopped animation feedback. Production rollout requires the migration and
coordinated API/worker/client versions; already issued operations may finish.

## Pin workflow destinations independently of discovery recency (12 October 2026)

**Situation:** Web Bill Entry inferred its destination from the account's newest
discovery. With several connected PCs, refreshing one machine could change the
implicit destination. Excel folder bindings could also change between launch and
approval, making a correct launch insufficient proof of the later write target.

**Task:** Make destination choice explicit and reusable for future workflows while
preserving account ownership, hosted execution, immutable approvals and retries.

**Action:** Add a shared destination picker and authenticated launch-envelope UUID.
Scope discovery by the chosen PC, pin that identity outside untrusted workflow
configuration, and validate catalog/folder agreement at launch and again at approval
under the source lock. Prevent native saves from targeting another PC or falling back
to browser grants. Keep absent destination fields out of legacy request fingerprints.
Exercise two-PC routing, delayed discovery responses, disappeared registrations,
folder rebinding and hosted-only proposals with synthetic integration/browser tests.

**Result:** Another PC's discovery recency no longer chooses Bill Entry's destination.
Future handlers receive an authorized, durable destination without new tool grants;
old launch retries and external-system recovery boundaries remain compatible.

## Resolve invoice names through pinned native identities (12 October 2026)

**Situation:** Exact invoice/ledger-name equality held routine bills despite complete
Discovery evidence. Formatting and OCR differences were confused with genuinely
new suppliers. Requiring approval for every native bill defeated exception-only mode.

**Task:** Let the hosted workflow recognize business identity from full evidence,
while keeping company authority, duplicate identity and consequential writes deterministic.

**Action:** Expose opaque discovery/company-scoped ledger references. Require the
workflow to cite identity evidence, then resolve every selection atomically to its
native canonical name before business validation and duplicate identity generation.
Reject foreign, invented, ambiguous and stale selections. Require a separate positive
new-supplier lookup outcome before the existing explicit native creation decision.
Preserve name-based legacy runs. Apply exception-only authorization to clean inputs
independently, scope child findings to their own input, and retain client-wide policy
gates and unchanged native identity/readback checks. Version and pin the revised bundle.

**Result:** Regression tests cover cross-company/catalog selections, Hindi and spelling
variants, duplicate native names, invalid lookup outcomes, supplier creation, sibling
isolation and approval policy. Live trials use scans, aliases and similarly named
suppliers across three companies; verified writes and exceptions remain auditable.

## Verify complete native evidence beyond successful export responses (12 October 2026)

**Situation:** Wider live Discovery returned vouchers outside requested date chunks.
Replacing the report with a native collection initially retained voucher identities
but omitted ledger allocation lines, making historical classification unnecessarily ambiguous.

**Task:** Collect truthful period-scoped, complete native evidence without sampling
or weakening byte, identity and period checks.

**Action:** Use a fixed read-only voucher collection and compare native calendar
components against validated numeric date bounds, avoiding native Date coercion.
Fetch the ledger and inventory subcollection aliases explicitly alongside the root
wildcard. Keep raw nested records intact and independently reject out-of-period dates.
Validate against the live exports, including allocation amounts and ledger identities,
instead of treating a successful XML status or record count as completeness proof.

**Result:** April–October collection succeeds for all three loaded companies and
retains the seeded vouchers' exact native allocations. Regression coverage checks
empty periods, nested data, failed exports, company changes and invalid dates.
The revised adapter ships in desktop 0.6.8; unsupported accounting structures remain held.

## Preserve independent diagnostics under business row locks (12 October 2026)

**Situation:** Validation held a workflow row with FOR UPDATE. A separate diagnostic
transaction needed a foreign-key key-share lock on that same row, timed out, and
discarded the diagnostic evidence it was intended to preserve across business rollback.

**Task:** Retain independent audit durability without committing business work early
or weakening serialization against operator controls.

**Action:** Use FOR NO KEY UPDATE for runtime mutations of immutable run identities.
The lock still excludes concurrent business updates and Stop while allowing the
diagnostic foreign-key check. Add a PostgreSQL regression that records a diagnostic
under the real business lock, rolls back the business transaction, and verifies the
diagnostic survives with tenant isolation intact.

**Result:** The reproduced timeout is resolved. Run controls and receipt regressions
continue to pass, and live validation now retains its internal stage diagnostics.

## Preserve separate tax identities through consequential writes (12 October 2026)

**Situation:** Real purchase bills supplied distinct CGST and SGST amounts, while
the adapter could represent only a single tax allocation. Collapsing those lines
would preserve a gross total while losing the accounting meaning.

**Task:** Support bounded split tax without letting old companions flatten a new
plan or letting two conflicting candidates choose an arbitrary first write.

**Action:** Extend the versioned proposal with separately evidenced company-scoped
tax references. Resolve them atomically, enforce exact cents and distinct ledgers,
preflight every candidate sharing an invoice identity, and hold all conflicting
versions. Negotiate native plan protocol 2 before delivering a split plan. Recheck
every master and verify each independent native allocation after import. Preserve
legacy single-tax runs and existing uncertainty/reconciliation fences.

**Result:** Regression tests reject invalid sums, foreign or repeated masters,
unsupported client versions, competing splits and collapsed receipts. Live proof
records the native outcome separately from extraction quality and operator review;
Tally date rejection remains an external-system handoff.
## Bound hosted stream persistence without weakening recovery (12 October 2026)

**Situation:** A production Source Discovery collected native sources quickly,
then waited about two minutes for its Cloud Run worker and another 154 seconds
for hosted interpretation. All 585 streamed events synchronously updated the
same recovery IDs and opened a separate diagnostic connection, including 492
text/output chunks. Durable bookkeeping sat directly on the stream-consumption path.

**Task:** Remove per-chunk persistence overhead while retaining paid-session
recovery, worker freshness and useful independent failure diagnostics.

**Action:** Commit newly observed session/turn IDs immediately, regardless of
which event first supplies them. Persist unchanged IDs at most once per ten-second
activity heartbeat. Aggregate chunk/item events into counts, flushing on that
heartbeat, lifecycle milestones and executor exit, including failure. Retain
individual lifecycle diagnostics and the existing raw-result-before-validation
commit. Keep this in the shared runtime, without another worker or audit schema.

**Result:** Regression tests cover hundreds of chunks without repeated session
writes, heartbeat timing, missing IDs on resumed streams, IDs first supplied on
a chunk, and disconnects retaining final activity counts. Existing runtime and
hosted-adapter tests pass. Production rollout and measured latency improvement
remain separate; this change does not remove cloud startup or model execution time.

## Separate complete source collection from optional AI interpretation (12 October 2026)

**Situation:** Native discovery finished before the cloud worker started, but
operators had to wait for subjective context notes and Excel meanings before
reviewing otherwise complete evidence.

**Task:** Permit deterministic-only discovery without implying that collected
Excel structure is a reviewed accounting destination or changing Bill Entry routing.

**Action:** Add an optional per-run boolean that defaults to AI-on for old callers.
AI-off retains full native collection, structure projection, completeness checks,
input bounds, persistence and explicit confirmation, and skips hosted dispatch.
Restore the choice from the previous run. Keep raw Excel structure without creating
semantic mappings or a destination catalog, and explain that consequence in setup
and review. Preserve Bill Entry's existing confirmed-catalog selection and pinning.

**Result:** PostgreSQL regressions verify direct review, confirmation, partial-scope
rejection and Excel formula preservation without a hosted run or fabricated mappings.
Browser coverage exercises all three source modes, choice restoration, AI-on selection,
confirmation and responsive layout. Production rollout remains separate.

## Reuse batch compute while preserving durable conversations (12 October 2026)

**Situation:** A production bill took 7m 29s to reach review, including 88.6 seconds
waiting for its hosted sandbox. Four independent bill lanes repeated that setup
for each input. Early Tally writes could bypass the existing comparison of all
versions of an invoice and therefore were unsuitable as a behavior-preserving fix.

**Task:** Reuse hosted compute across a batch without merging bill conversations,
weakening operator controls, replaying paid work, or changing review and writes.

**Action:** Reserve four PostgreSQL-backed environment slots per operator's parent
run. Hold advisory locks through provisioning, uploads and extraction; require a
confirmed session cleanup receipt before reuse. Pin profile and resource grants,
rotate expired or failed environments and enforce the provider attachment limit.
Use fresh per-run inputs, full skill bundles and output namespaces, rebinding only
trusted execution paths and derived lookup references. Save workspace metadata
before submitting input; recover saved sessions without provisioning or uploading.
Clear inherited cleanup receipts on retry children. Retain the complete-batch
duplicate checks and consequential-write sequence.

**Result:** PostgreSQL and adapter regressions cover contention, cleanup gates,
worker rotation, changed grants, expiry, attachment limits, Stop and ambiguous
creation. Two synthetic live sessions reused the same environment with distinct
verified outputs and completed-turn recovery; their total times were 50.8s and
36.5s. These are capability checks, not customer batch benchmarks. Production
rollout and measured customer latency remain separate; Cloud Run's initial startup
and bill reasoning still contribute to elapsed time.


### 2026-10-12 — Consistent workflow configuration and truthful outcomes

**Situation:** Workflow-specific launch forms and a generic settings panel exposed overlapping controls with different state lifetimes. Tally approval copy contradicted exception-only execution, and findings could conceal verified saves.

**Task:** Make the frontend reflect durable execution semantics without changing accounting rules or destination selection.

**Action:** Consolidated editable defaults into a shared run-options component, kept schema-declared defaults separate from resource selections, isolated workflow administration, and made previous-run reuse explicit. Save outcomes take precedence over findings, with attention linked separately. Added regression coverage for default persistence boundaries, failed saves, role restrictions, resource routing and responsive layouts.

**Result:** Run options have one visible home; saving defaults never changes availability or an executing run. Discovery identifies run-only options explicitly. Verification and attention remain separate, and displayed wall time derives from recorded timestamps rather than estimates.
