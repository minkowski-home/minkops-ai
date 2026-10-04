# Decision Logs

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
