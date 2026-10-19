# Data warehouse plan

Status: **approved plan, not yet implemented** (17 October 2026).
Execution scope now: **local PostgreSQL warehouse for development and testing.**
Production tools (BigQuery, Datastream, Airflow, BI) are described as the next
step and must not be built until their gates in [Phase 5](#phase-5--production-path-next-not-now) are met.

This document is written for the engineer who builds the warehouse. Every step
says **what** to do, **how** to do it and **why** it is done that way, so that
decisions survive the people who made them. Read it top to bottom once before
starting; then work phase by phase. Do not skip Phase 0.

**For the AI reading this:** High-level decisions are mostly locked, but low-level implementation-time decisions 
need not be taken word-to-word; if something else makes more sense at build time, 
feel free to flag it or drift from this plan.

---

## Contents

1. [Concepts in five minutes](#1-concepts-in-five-minutes)
2. [Goals and non-goals](#2-goals-and-non-goals)
3. [Decisions at a glance](#3-decisions-at-a-glance)
4. [Architecture](#4-architecture)
5. [Phase 0 — OLTP corrections](#phase-0--oltp-corrections-prerequisites)
6. [Phase 1 — Local warehouse foundation](#phase-1--local-warehouse-foundation)
7. [Phase 2 — Staging layer](#phase-2--staging-layer)
8. [Phase 3 — Internal marts](#phase-3--internal-marts)
9. [Phase 4 — CI, runbook and documentation](#phase-4--ci-runbook-and-documentation)
10. [Phase 5 — Production path (next, not now)](#phase-5--production-path-next-not-now)
11. [Phase 6 — Customer analytics suite (designed, gated)](#phase-6--customer-analytics-suite-designed-gated)
12. [Risk and failure-mode register](#12-risk-and-failure-mode-register)
13. [Edge cases checklist](#13-edge-cases-checklist)
14. [Open questions](#14-open-questions)
15. [Appendix A — OLTP table inventory](#appendix-a--oltp-table-inventory)

---

## 1. Concepts in five minutes

| Term | Meaning | Where it shows up here |
| --- | --- | --- |
| **OLTP** | The application database: many small reads/writes, current state. | `db/migrations`, database `minkops_app`. |
| **Warehouse (OLAP)** | A separate database optimised for analysis over history. Never the source of truth for product features. | Database `minkops_warehouse` (local), BigQuery later. |
| **EL (extract–load)** | Copying source data into the warehouse unchanged. | Phase 1 loader, later Datastream or Airbyte. |
| **T (transform)** | Turning raw copies into clean, tested models with SQL. | dbt, Phases 2–3. |
| **Full refresh** | Copy the whole table every run and replace the copy. Always correct, cost grows with table size. | Default load mode for small tables. |
| **Incremental (cursor / high-watermark)** | Copy only rows with `cursor > last value seen`. Cheap but fragile (see §12). | Append-only tables. |
| **CDC (change data capture)** | Read every insert/update/delete from Postgres' write-ahead log (WAL) through logical replication. Sees deletes, commit-ordered, near-zero source load. | Production, Phase 5. |
| **Hard vs soft delete** | Hard: row removed. Soft: row kept with `deleted_at`. Cursors cannot see hard deletes. | §12, Appendix A. |
| **Medallion layers** | bronze/silver/gold ≙ dbt's raw/staging/marts. | §4 layer table. |
| **Grain** | What one row of a model represents ("one row per workflow run"). Every fact model must state it. | Phase 3. |
| **SCD2 / snapshot** | Keeping every historical version of a mutable row with validity ranges. | Deferred until the first real client write (Phase 5). |
| **Pool / Bridge / Silo** | Multi-tenant isolation: shared tables keyed by tenant / schema per tenant / database per tenant. | Phase 6. |

---

## 2. Goals and non-goals

### Goals (this stage)

1. **Prove the pipeline and its guarantees, not the volume.** Every in-scope OLTP
   table lands in `raw`, is cleaned in `staging`, and is tested (keys, relations,
   accepted values, freshness, tenant scoping).
2. **Answer launch-readiness questions** from operational metadata (Phase 3):
   run success and duration, attention-item resolution time, write verification
   rates, Windows companion job health.
3. **Make schema drift impossible to miss.** A migration that breaks the
   warehouse fails CI (Phase 4).
4. **Govern data from day one.** Secrets never leave the OLTP; personal data is
   pseudonymised in staging; customer business payloads are not extracted until
   the Phase 6 policy gate.
5. **Stay portable.** SQL and layout must move to BigQuery (or stay on Postgres)
   with an adapter swap, not a rewrite.

### Non-goals (this stage)

Real-time analytics, ML, reverse ETL, product clickstream, dashboards for
customers, snapshots/history, production hosting, Airflow, Airbyte.

### Who uses it

Minkops engineers and founders, via SQL (psql, DBeaver, any Postgres client).
No BI tool is required locally.

---

## 3. Decisions at a glance

| # | Decision | Choice now | Why | Revisit when |
| --- | --- | --- | --- | --- |
| D1 | Dev warehouse engine | **Local PostgreSQL 16**, database `minkops_warehouse` in the existing Compose container | Zero new infrastructure; a Postgres warehouse is a legitimate production option up to a few hundred GB. | Phase 5 gate. |
| D2 | Production warehouse | **BigQuery (default candidate)**, decided at ship time | GCP-native, serverless (≈ $0 idle), free tier covers early volume. | Ship time, with real volume and budget. |
| D3 | Extraction (dev) | **`postgres_fdw` + a small manifest-driven loader** | No new tool to learn or run; the manifest is the reusable extraction contract. | Replaced in Phase 5. |
| D4 | Extraction (prod) | **Datastream CDC** if BigQuery; **Airbyte** if the warehouse stays elsewhere. Chosen together with D2. | Datastream only targets BigQuery/GCS. Self-hosted Airbyte (~CAD 100+/month) exceeds the post-launch budget. | Phase 5. |
| D5 | Transformation | **dbt-core + dbt-postgres** (exact pins) | Industry standard, portable, orchestrator-agnostic. | — |
| D6 | Orchestration | **None locally** (one CLI command). Prod: Cloud Scheduler → Cloud Run Job; **self-hosted Airflow + Astronomer Cosmos** at ≥ 2 sources or dependent schedules. | Airflow for a two-step DAG is overhead; adding it later costs about a day because dbt does not depend on it. Not Cloud Composer: its floor cost is ~USD 300+/month. | Second source. |
| D7 | History (snapshots) | **None until the first production write into a real client system** | History before then has no value to us. Snapshots are additive; nothing built earlier changes. | First real client write (release checklist item). |
| D8 | Tenancy model | **Build pooled, serve bridged**: pooled layers with `tenant_id` everywhere; per-tenant schemas containing views only, for the customer suite | The OLTP is pooled, so raw arrives pooled regardless of hosting; per-tenant views give Bridge's access boundary without N× builds. | Enterprise contract requiring physical isolation. |
| D9 | Test tenant | **Exclude `mock-tenant`** (all testing, demos and production verification use it) via a dbt variable now, `tenants.kind` after Phase 0 | `scripts/verify_production.py` and `provision_demo.py` also use `mock-tenant` in production. | When `kind` exists. |
| D10 | Customer business data | **Not extracted** until the Phase 6 policy gate; design exists now | Ledger and bill data need a deliberate data policy and DPA. | Analytics suite kickoff. |
| D11 | `tenants.industry` | **Deferred** to Phase 6 as a controlled classification | Free text breaks benchmarking; a lookup/standard code must be designed with the suite. | Phase 6. |
| D12 | Open source vs managed | Managed for stateful storage and near-zero idle cost; open source for logic layers; avoid managed services with high floor cost | Portability where logic lives, no operations burden where data lives. | — |

Open source vs managed, per concern (D12):

| Concern | Managed | Open source | Pick |
| --- | --- | --- | --- |
| Object storage | GCS | MinIO | Managed |
| Warehouse | BigQuery | Postgres / ClickHouse / DuckDB | Postgres now, decide at ship |
| Transform | Dataform | dbt-core | dbt |
| Orchestration | Cloud Composer | Airflow on a VM | Open source, when needed |
| CDC | Datastream | Debezium (needs Kafka/Connect) | Managed |
| BI (internal) | Looker Studio (free) | Metabase / Superset | Looker Studio in prod |
| BI (embedded, customers) | Looker (expensive) | Superset (Metabase interactive embedding is paid) | Evaluate in Phase 6 |
| Quality / catalog | Dataplex | dbt tests + dbt docs | Open source |

---

## 4. Architecture

### Local (this plan)

```
infra/compose.yml  ── postgres:16 container (127.0.0.1:5433)
  ├─ database minkops_app          (OLTP; migrations in db/)
  │    role warehouse_reader  ── SELECT on allow-listed tables/columns only
  │
  └─ database minkops_warehouse    (warehouse)
       ext_oltp      foreign tables via postgres_fdw  (never queried by dbt)
       raw           landed copies + _loaded_at/_load_id   (loader writes)
       staging       dbt views: typed, renamed, pseudonymised (silver)
       intermediate  dbt: joins and state logic
       marts         dbt tables: facts and dimensions for internal metrics (gold)
       <dev schemas> dbt_<engineer>_*  personal build targets
```

Run: `uv run --project warehouse python -m minkops_warehouse run`
→ acquire lock → load raw → `dbt build` → `dbt source freshness`.

### Production (Phase 5, for orientation only)

```
Cloud SQL (dedicated instance) ─ read replica ─► Datastream CDC ─► BigQuery raw
                                                                     │
                       Cloud Scheduler ─► Cloud Run Job (dbt build) ─┘─► staging/marts
                                                     (later: Airflow + Cosmos)
                                                                     └─► Looker Studio
```

### Layer contract

| Layer | Owner | Materialization | Rules |
| --- | --- | --- | --- |
| `ext_oltp` | Loader bootstrap | foreign tables | Only the loader reads it. Never referenced from dbt. |
| `raw` | Loader | tables | Source columns unchanged + `_loaded_at timestamptz`, `_load_id uuid`. Later CDC adds `_op`, `_source_deleted`, `_commit_lsn`. |
| `staging` | dbt | views | 1:1 with raw tables. The **only** layer allowed to `source()` raw. Rename, cast, pseudonymise, unpack documented JSON fields. No joins. |
| `intermediate` | dbt | ephemeral/views | Joins and reusable logic. Not exposed to users. |
| `marts` | dbt | tables | Facts/dimensions with a stated grain; every model carries `tenant_id`; analytics tenants filtered here. |

Why "only staging reads raw": when the extraction tool changes (fdw → Datastream
or Airbyte, each with its own metadata columns and type mapping), only source
definitions and staging change. Nothing downstream is touched.

---

## Phase 0 — OLTP corrections (prerequisites)

These were found while auditing the schema. They are worth fixing **even with
no warehouse**, and several block reliable extraction. Each item is its own
small branch, migration and PR.

### 0.0 Migration rules (read before touching `db/`)

- **Never edit an applied migration, not even a comment.** `db/migrate.py`
  stores a SHA-256 of every file and refuses to run (`Applied migration changed`)
  when any byte differs, on production and every developer database. The single
  allowed baseline variant (`BASELINE_FORMAT_CHECKSUMS`) is a one-time exception
  for a reviewed formatting change, not a mechanism for comments.
- New changes go in `db/migrations/0008_*.sql`, `0009_*.sql`, … in order.
- Use **expand → migrate → contract**: add nullable column, deploy code that
  writes it, backfill, then add `NOT NULL`/drop the old thing in a later
  migration. This keeps the old and new app versions working during a deploy.
- `db/tests` already compares fresh vs upgraded schemas; every Phase 0 migration
  adds assertions there (fresh install, upgrade with existing rows).
- Large backfills run in batches outside the schema migration if a table is big;
  today every table is small, so in-migration backfills are acceptable but must
  be idempotent.

### 0.1 Separate the meanings of `updated_at`, then make it trigger-maintained

**What is wrong.** Only 5 tables have `updated_at` (`tasks`, `workflow_runs`,
`attention_items`, `desktop_jobs`, `discovery_runs`), set by about 21
hand-written `updated_at=now()` assignments with no trigger. A forgotten line
leaves the value silently wrong. Worse, the column carries **several unrelated
meanings** today:

| Usage | Location | Meaning actually needed |
| --- | --- | --- |
| Stale `executing` runs reclaimed after 30 s | `platform/src/minkops_platform/runtime/store.py:14` | worker **heartbeat/lease** |
| Queue order `ORDER BY updated_at` | `runtime/store.py:18`, `:49` | **queued at** |
| Queue time shown for queued runs | `runtime/lifecycle.py:153` | **queued at** |
| Attention refresh sweep order and "touch" | `platform/src/minkops_platform/attention.py:131`, `:140` | **last refreshed/checked at** |
| Lists sorted by recent activity | `attention.py:91`, `accounts/repository.py:120`, `apps/solution-api/src/minkops_api/workspace.py:59` | **row last changed** |
| Cleanup bookkeeping deliberately *not* bumping it | `runtime/store.py:51` (writes `config.cleanup_attempt_*`) | must not reorder lists |

**Why not just add a trigger.** A trigger bumps `updated_at` on every update.
Then the cleanup bookkeeping update reorders "recent runs", any review update
pushes a run back in the queue order, and a heartbeat and a business change
become indistinguishable. Changing worker leasing by accident is a production
incident.

**How.**
1. Migration adds purpose-specific columns:
   - `workflow_runs.queued_at timestamptz` (backfill: `updated_at` for queued
     rows, `created_at` from 0.2 otherwise) and `workflow_runs.heartbeat_at timestamptz`
     (set when claimed and on progress; backfill from `updated_at` for executing rows).
   - `attention_items.refreshed_at timestamptz` (backfill from `updated_at`).
2. Code change (same PR or immediately after): queue and lease queries use
   `queued_at`/`heartbeat_at`; the refresh sweep uses `refreshed_at`. Add tests
   that a review update does not reorder the queue and that a stale heartbeat is
   reclaimed while a fresh one is not.
3. Move cleanup bookkeeping out of `workflow_runs.config` (the request
   configuration) into dedicated columns `cleanup_attempt_at`,
   `cleanup_attempt_count`, `hosted_session_closed`. `config` should mean "what
   was requested", not operational state.
4. Add one shared trigger function and attach it to **every mutable table**:

   ```sql
   CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
   BEGIN
     -- Only real changes count: a no-op UPDATE must not look like activity.
     IF ROW(NEW.*) IS DISTINCT FROM ROW(OLD.*) THEN
       NEW.updated_at := now();
     END IF;
     RETURN NEW;
   END $$;
   ```
   Mutable tables without the column get `updated_at timestamptz NOT NULL DEFAULT now()`
   (see Appendix A, column "Mutable"). The `IS DISTINCT FROM` check must compare
   the row *before* the trigger sets `updated_at`, which it does.
5. Remove the hand-written `updated_at=now()` assignments in a follow-up once
   the trigger is live; they become redundant but harmless.

**Note for the warehouse:** even a trigger-maintained `updated_at` is only a
*cursor candidate*. It still suffers commit-time skew (§12, R2), so the
warehouse uses it with a lookback window, never alone.

### 0.2 Missing creation timestamps

**What.** `workflow_runs` has no `created_at` (only `updated_at`), so request
time and queue latency are unknowable. `account_writes` and `account_catalogs`
have no timestamps at all.

**How.** Add `created_at timestamptz` (nullable), backfill, then `SET NOT NULL`
and `DEFAULT now()`:
- `workflow_runs.created_at`: backfill from the parent `tasks.created_at`, and
  for child runs from the parent run, else `updated_at`. Record in the
  migration comment that pre-migration values are **approximate**.
- `account_writes.created_at`: backfill from the owning run's `created_at`.
- `account_catalogs.created_at`: backfill from `confirmed_at` when present, else
  the migration time; add `updated_at` too if the catalog is mutable.

**Why not `DEFAULT now()` on add:** that stamps every existing row with the
migration time, which is a confident lie. Approximate-but-honest beats precise-but-wrong;
the warehouse marks pre-migration rows with a `created_at_is_backfilled` flag
derived from the migration timestamp.

### 0.3 Tenant classification: `tenants.kind`

**What.** `tenants` is only `(id, slug, name, created_at)`. Excluding tenants by
slug breaks once there is a second demo or a staging tenant.

**How.** `kind text NOT NULL DEFAULT 'customer' CHECK (kind IN ('customer','internal','demo'))`;
backfill `mock-tenant` → `internal`. Update `scripts/provision_demo.py` and
`db/seed_demo.py` to set `kind` explicitly. Signup keeps the default.
Also add `updated_at` + trigger (tenants are renamed).

**Deferred:** `industry` (D11) and a tenant `timezone` (needed for per-tenant
"daily" metrics in Phase 6; see §14).

### 0.4 Move file bytes out of the OLTP (independent track)

**What.** Both `account_files.content` and `account_writes.content` are `bytea`
holding whole files (Excel workbooks and approved write bytes). This bloats the
database, every backup and restore, and would be copied by every extraction
strategy (full refresh copies it every run; CDC streams it through the WAL).

**Design.**
- An object-store adapter in `connectors/` with two implementations: GCS
  (production) and local filesystem (dev/tests). Platform code depends only on
  the interface.
- **Content-addressed keys:** `tenants/<tenant_id>/files/<sha256>`. Both tables
  already store hashes (`sha256`, `before_sha256`, `after_sha256`), so
  identical bytes deduplicate and integrity is verifiable on read.
- **Write ordering:** upload object first, then commit the row referencing it.
  A crash leaves an orphan object (harmless, garbage-collected), never a row
  pointing to nothing. Readers verify the hash after download.
- **Orphan GC:** a periodic job deletes objects older than 24 h that no row
  references.
- **Tenant deletion:** deleting a tenant must delete its prefix; add this to the
  tenant offboarding procedure.
- **Security:** bucket private, uniform access, per-service-account IAM, object
  versioning off (content is immutable by hash), retention aligned with the
  OLTP rows.
- **Rollout (expand/contract):** add `content_key text` → dual-write → batch
  backfill existing rows → switch reads → drop `content` in a later migration.

This track does **not** block Phases 1–4: the warehouse never extracts these
columns (Appendix A). It is a pre-launch item for database health.

### 0.5 Diagnostics retention vs warehouse history

**What.** `desktop_diagnostics` rows are deleted after 30 days
(`platform/src/minkops_platform/desktop.py:151`). `workflow_run_diagnostics`
is telemetry of the same kind. The right pattern is a short hot window in the
OLTP and long history in the warehouse.

**Consequence for the loader:** these tables must be loaded **append-only**
(merge by primary key, never truncate-and-replace), otherwise each full refresh
would delete the history the warehouse is meant to keep. Loads must run far
more often than the retention window (at least daily locally when in use;
hourly in production).

**Later:** once the warehouse holds the history, give `workflow_run_diagnostics`
an explicit retention job too, and document both windows in one place.

**Capture boundary:** keep Cloud Logging and OpenAI as the detailed operational
log viewers; do not mirror their raw streams into the warehouse. Persist the
allow-listed diagnostic metadata needed for correlation and history in the
existing product diagnostic tables: run/task/device identifiers, provider
session/turn identifiers, pinned definition/build, stage, timings, error class,
HTTP/SQL status and sanitized outcome. Capture these before deleting a hosted
session; a provider dashboard is not durable evidence after session deletion.
Missing capture is an operational instrumentation prerequisite, not a change to
the warehouse engine or extraction strategy. Raw prompts, documents, credentials,
local paths and unrestricted provider payloads remain excluded. Apply the same
allow-list, tenant access and erasure rules when adding any diagnostic fields.

### 0.6 Tracking

Log each Phase 0 change in `docs/decisions-log.md` only when it is interview-worthy
(0.1 lease/heartbeat separation and 0.4 content addressing qualify).

---

## Phase 1 — Local warehouse foundation

### 1.1 Project layout

```
warehouse/
  README.md                  # how to run; links here
  pyproject.toml             # standalone uv project with its own uv.lock
  src/minkops_warehouse/
    __main__.py              # CLI: bootstrap | load | run
    bootstrap.py             # database, roles, fdw, schemas (idempotent)
    load.py                  # manifest-driven loader
  extract/tables.yml         # extraction manifest (the contract; see 1.4)
  dbt/
    dbt_project.yml
    profiles.yml             # env-var driven, no secrets
    packages.yml             # dbt_utils (pinned)
    models/{staging,intermediate,marts}/
    macros/  tests/  seeds/  analyses/
  tests/                     # pytest for bootstrap/loader + contract checks
```

**Why a standalone uv project, not a workspace member:** the root
`pyproject.toml` workspace shares one lockfile. dbt-core pins many transitive
packages (protobuf, networkx, jsonschema …) that would constrain or conflict
with the application's dependencies. A separate project isolates them. Cost:
CI runs `uv sync --project warehouse` separately (Phase 4).

**Why `minkops_warehouse` imports nothing from `platform/`, `apps/` or
`connectors/`:** the warehouse's only contract is the database schema. Importing
app code would couple release cycles and leak business logic into analytics.

**Pins:** Python 3.12 (repo standard), `dbt-core` and `dbt-postgres` at the
latest 1.x patch on the day of implementation, pinned exactly; `psycopg[binary]`
as in `db/`. dbt Fusion is not used: its Postgres support lags the BigQuery
adapters, and dbt-core keeps both paths open.

### 1.2 Bootstrap: database, roles, extensions (idempotent)

Postgres' Docker init scripts only run on an **empty** volume, so existing
developer volumes would never run them. Bootstrap is therefore an idempotent
command: `python -m minkops_warehouse bootstrap`, safe to run any number of
times, using the Compose superuser locally.

Steps:
1. `CREATE DATABASE minkops_warehouse` if missing.
2. Roles (all `NOLOGIN` groups plus login users with env-provided passwords):

   | Role | Database | Grants | Purpose |
   | --- | --- | --- | --- |
   | `warehouse_reader` | `minkops_app` | `SELECT` on allow-listed tables, **column-level** grants only for allow-listed columns | What the fdw connects as. Secrets are unreadable even by mistake. |
   | `warehouse_loader` | `minkops_warehouse` | owns `raw`, usage on `ext_oltp` | Loader. |
   | `warehouse_transformer` | `minkops_warehouse` | read `raw`; owns `staging`, `intermediate`, `marts`, `dbt_*` | dbt. |
   | `warehouse_analyst` | `minkops_warehouse` | read `marts` only | Humans and future BI. |

   Grants are generated from `extract/tables.yml`, so the manifest is the single
   place that decides what leaves the OLTP. New OLTP tables are invisible until
   added (deny by default).
3. `CREATE EXTENSION postgres_fdw` (warehouse DB) and `pgcrypto` (for
   pseudonymisation).
4. `CREATE SERVER oltp FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host, port, dbname 'minkops_app', fetch_size '10000')`
   and a user mapping for `warehouse_loader` → `warehouse_reader`.
5. `IMPORT FOREIGN SCHEMA public LIMIT TO (<manifest tables>) FROM SERVER oltp INTO ext_oltp`
   (re-imported on every bootstrap after dropping `ext_oltp`, so new columns
   appear; column grants still hide disallowed ones, and the loader selects
   explicit columns only).
6. Create schemas `raw`, `staging`, `intermediate`, `marts`.

Inside the container, the fdw host is `localhost` (same server). This must be
configurable for CI and for anyone running a separate container.

### 1.3 Loader

`python -m minkops_warehouse load` reads the manifest and, per table:

| Mode | SQL shape | Use for |
| --- | --- | --- |
| `full_refresh` | `TRUNCATE raw.t; INSERT INTO raw.t SELECT <cols>, now(), :load_id FROM ext_oltp.t` | Small, mutable tables. |
| `append_merge` | `INSERT … SELECT … WHERE <cursor> > :watermark - :lookback ON CONFLICT (<pk>) DO UPDATE` | Append-only/event tables and tables with retention deletes (0.5). |

Rules and reasons:
- **One local transaction for the whole load.** postgres_fdw opens one remote
  transaction per local transaction at `REPEATABLE READ`, so every table is read
  from **one consistent snapshot** of the OLTP. Separate transactions would let
  a run land in `raw.workflow_runs` without its task in `raw.tasks`, breaking
  relationship tests intermittently.
- **Explicit column lists** from the manifest, never `SELECT *`. A new OLTP
  column is not extracted until someone decides it should be.
- **Watermarks** stored in `raw._load_state(table, watermark, load_id, loaded_at)`;
  updated in the same transaction as the data, so a failed load never advances
  the watermark.
- **Lookback** (default 10 minutes) re-reads the tail on every run to catch
  rows whose transaction started before the previous load but committed after
  it (commit-time skew, §12 R2). `ON CONFLICT` makes the overlap idempotent.
- **Concurrency guard:** `pg_try_advisory_lock` on a fixed key at start; a
  second run exits with a clear message. (`db/migrate.py` uses the same pattern.)
- **Load audit:** `raw._load_runs(load_id, started_at, finished_at, status, rows_per_table jsonb, error)`.
- `raw` tables are created from the manifest on bootstrap with the source's
  column types plus `_loaded_at`, `_load_id`; type changes in the source fail
  the load loudly (contract test, Phase 4) rather than coercing silently.

### 1.4 Extraction manifest (`extract/tables.yml`)

The manifest is the most important artefact in this phase; any future EL tool
is configured from it.

```yaml
defaults:
  mode: full_refresh
tables:
  workflow_runs:
    primary_key: [id]
    columns: [id, tenant_id, task_id, actor_id, workflow_key, definition_version,
              request_key, catalog_id, state, review_actor_id, reviewed_at, error,
              updated_at, parent_run_id]   # add created_at/queued_at/heartbeat_at after Phase 0
    excluded:
      config: business payload; Phase 6 policy gate
      result: business payload; Phase 6 policy gate
      file_ids: business payload; Phase 6 policy gate
      session_id: provider identifier, not needed
      turn_id: provider identifier, not needed
      request_hash: internal idempotency
  desktop_diagnostics:
    mode: append_merge
    cursor: created_at
    primary_key: [id]
    ...
excluded_tables:
  sessions: authentication secrets
  email_verifications: authentication secrets
  worker_wakeup: process coordination state
```

A pytest check (Phase 4) fails when any OLTP table is in neither `tables` nor
`excluded_tables`, and when any column of an included table is in neither
`columns` nor `excluded`. Nothing new leaves or is forgotten silently.
Appendix A gives the starting manifest.

---

## Phase 2 — Staging layer

### 2.1 dbt configuration

- `profiles.yml` in the repo, reading `WAREHOUSE_HOST`, `WAREHOUSE_PORT`,
  `WAREHOUSE_USER`, `WAREHOUSE_PASSWORD`, `DBT_SCHEMA_PREFIX`. Targets: `dev`
  (personal prefix, e.g. `dbt_kartik`) and `ci`.
- Override `generate_schema_name` so `dev` builds into `dbt_<name>_staging` etc.
  and `ci`/`prod` build into the real schema names. Engineers never overwrite
  each other or the shared schemas.
- Folder-level defaults in `dbt_project.yml`: staging = view, intermediate =
  ephemeral, marts = table.
- Packages: `dbt_utils` only, pinned.

### 2.2 Conventions

| Item | Convention |
| --- | --- |
| Model names | `stg_oltp__<table>`, `int_<entity>_<verb>`, `fct_<process>`, `dim_<entity>` |
| Keys | `<entity>_id`; never a bare `id` outside staging |
| Timestamps | `<event>_at`, `timestamptz`, stored in UTC |
| Booleans | `is_`/`has_` |
| Enums | lower-case text; accepted values mirror the OLTP `CHECK` constraints |
| Portability | Use dbt cross-database macros (`dbt.date_trunc`, `dbt.datediff`, `dbt.type_string`, `dbt.safe_cast`). Postgres-only syntax (`DISTINCT ON`, `->>`, `::`, `FILTER`) is allowed only inside staging, and JSON access goes through one macro (`json_text(col, 'key')`) so the BigQuery port changes one file. |

### 2.3 Staging model rules

- One model per raw table; select explicit columns; rename to conventions; cast.
- **Pseudonymisation:** `users.email` → `email_hash = encode(hmac(lower(email), '<key>', 'sha256'), 'hex')`
  with the key from env var `WAREHOUSE_PII_KEY` (dbt `env_var`). Also derive
  `email_domain` (useful for "which company") and drop `name`. HMAC rather than
  plain SHA-256 because unsalted email hashes are reversible by dictionary.
  Same for `invitations.email`.
- **JSON:** staging may unpack only documented, non-business fields (for
  example diagnostics `details.code`), keyed by `definition_version` where
  shapes differ.
- **No tenant filtering here.** `mock-tenant` stays visible in staging for
  debugging; filtering happens in marts.

### 2.4 Tests on every staging model

- Primary key `unique` + `not_null`.
- `relationships` for each tenant-composite foreign key (test `tenant_id` and
  the referenced id together using `dbt_utils.relationships_where` or a custom
  generic test `tenant_relationship`).
- `accepted_values` for every status/state column, copied from the OLTP
  `CHECK` constraints. A Phase 4 check compares them to the live constraints
  so they cannot drift.
- `not_null` on `tenant_id` for every tenant table.
- **Source freshness** on `_loaded_at` (warn 24 h, error 72 h locally; tightened
  in production).
- dbt **unit tests** (dbt ≥ 1.8) for any non-trivial logic.

---

## Phase 3 — Internal marts

Filter rule: every mart joins `dim_tenants` and keeps only `is_analytics_tenant`.
Until `tenants.kind` exists, that is `slug NOT IN var('excluded_tenant_slugs')`
with default `['mock-tenant']`; afterwards it is `kind = 'customer'`, keeping
the variable as an override. The variable also lets an engineer include
`mock-tenant` locally (`--vars`) to see data at all before launch, which is
the normal local workflow.

### 3.1 Dimensions

| Model | Grain | Notes |
| --- | --- | --- |
| `dim_tenants` | one row per tenant | `kind`, `is_analytics_tenant`, created date |
| `dim_users` | one row per user | hashed email, domain, `is_platform_admin`, verified flag |
| `dim_memberships` | one row per tenant × user | role |
| `dim_workflows` | one row per workflow | key, status, employee links |
| `dim_employees` | one row per employee | key, status |
| `dim_desktop_devices` | one row per device | companion version, revoked/expired, last seen |
| `dim_date` | one row per UTC day | `dbt_utils.date_spine` |

### 3.2 Facts

| Model | Grain | Key measures |
| --- | --- | --- |
| `fct_workflow_runs` | one row per run (top-level runs; child runs rolled up) | final state, queue latency (`queued_at`→first heartbeat, after Phase 0), wall time to terminal state, reviewed?, review latency, failed with/without error |
| `fct_task_events` | one row per task event | event type, progress |
| `fct_attention_items` | one row per attention item | kind, status, time to done, done by actor type, created by which run/workflow |
| `fct_attention_events` | one row per attention action | action, actor |
| `fct_tally_writes` | one row per Tally write | outcome, verified?, cancelled?, time to verify |
| `fct_file_writes` | one row per Excel write | verified?, cancelled? |
| `fct_desktop_jobs` | one row per desktop job | operation, attempts, final state, duration |
| `fct_discovery_runs` | one row per discovery run | state, duration, confirmed? |
| `fct_diagnostics_daily` | one row per tenant × day × kind | counts by level/kind |

### 3.3 First metrics (definitions live in model YAML descriptions)

| Metric | Definition | Caveat |
| --- | --- | --- |
| Run success rate | completed ÷ (completed + failed), terminal runs, by workflow and week | Current state only; no transition history until D7. |
| Queue latency p50/p90 | queued → started | Requires Phase 0.1/0.2. |
| Review latency | entered review → `reviewed_at` | "Entered review" is approximate without history; use `task_events` where available. |
| Attention resolution time | `done_at - created_at` for done items; age for pending | — |
| Best-guess share | attention items of best-guess kind ÷ written records | **Definition to confirm with product** (§14). |
| Write verification rate | verified ÷ (verified + cancelled + pending > 24 h) for Tally and Excel writes | — |
| Companion job failure rate | failed ÷ terminal desktop jobs, by companion version | — |

---

## Phase 4 — CI, runbook and documentation

### 4.1 CI (new job in `.github/workflows/validate.yml`)

1. Start `postgres:16` service (as the backend job does).
2. `uv sync --frozen --project warehouse`.
3. Create `minkops_app`, run `db/migrate.py`, run `db/seed_demo.py` (the same
   fixtures the app tests use).
4. `python -m minkops_warehouse bootstrap` then `load`.
5. `dbt deps`, `dbt build --target ci --vars '{excluded_tenant_slugs: []}'`
   (include `mock-tenant` so models have rows), `dbt source freshness`.
6. pytest in `warehouse/tests`:
   - manifest covers every OLTP table and column (1.4);
   - `accepted_values` match OLTP `CHECK` constraints (parsed from
     `information_schema`/`pg_constraint`);
   - every `marts` model has a `tenant_id` column with a `not_null` test (read
     from dbt's `manifest.json`);
   - no model outside `staging` calls `source()`;
   - loader idempotency: loading twice yields identical raw row counts; an
     `append_merge` table keeps rows deleted from the source.

**Why this matters most:** it turns "a migration silently broke analytics" into
a failing PR on the migration itself, which is where the fix belongs.

### 4.2 Runbook (`warehouse/README.md`)

- First-time setup: `docker compose -f infra/compose.yml up -d`, migrate, seed,
  `bootstrap`, `run`.
- Daily: `run`.
- Reset: drop `minkops_warehouse` and re-bootstrap (the warehouse is always
  rebuildable from the OLTP except `append_merge` history, which is acceptable
  locally).
- Troubleshooting: lock held, freshness errors, fdw authentication, new OLTP
  column not appearing (manifest).

### 4.3 Documentation

- `dbt docs generate` locally; every model and column described in YAML.
- Update the root `README.md` repository map entry for `warehouse/`.
- Decisions-log entries for interview-worthy items only.

**Done for the local phase** = Phases 0.1–0.3 merged, 1–4 merged, CI green,
`run` completes from a fresh clone in under 10 minutes using only the README.

---

## Phase 5 — Production path (next, not now)

Gates, in order. Do not start a step before its gate.

| Step | Gate | What | Notes |
| --- | --- | --- | --- |
| P1 | Before first real users | **Dedicated Cloud SQL instance** for the Minkops OLTP | Hosting change only; does not change tenancy (§ D8). Enables safe flag changes, own maintenance windows. |
| P2 | P1 done; budget extended to ~$45–60 | **Choose warehouse** (default BigQuery) and **region** | Region must satisfy the data-residency answer (§14). Dataset per layer; partition facts by date, cluster by `tenant_id`. |
| P3 | P2 | **CDC**: enable `cloudsql.logical_decoding` (restarts the instance: schedule it), create a **read replica** if supported for the source, set up Datastream (BigQuery) or Airbyte, publication limited to manifest tables, column exclusions from the manifest | **Monitor replication-slot lag and retained WAL with an alert.** An abandoned slot retains WAL until the disk fills and takes the OLTP down. Configure `max_slot_wal_keep_size`. |
| P4 | P3 | **Port dbt**: adapter `dbt-bigquery`, `generate_schema_name` → datasets, replace the JSON macro, CDC metadata → raw contract (`_op`, `_source_deleted`), dedupe latest row per key in staging | Thanks to Phase 2 rules, only staging and macros change. |
| P5 | P4 | **Run**: Cloud Scheduler → Cloud Run Job (`dbt build` + freshness), same pattern as the accounts worker; service accounts and datasets provisioned by `infra/provision_warehouse.py` | IaC belongs in `infra/`, runtime config in `warehouse/`. |
| P6 | First production write into a real client system | **Enable dbt snapshots** (check strategy on `updated_at`, after Phase 0.1) for `workflow_runs`, `attention_items`, `tasks`, `desktop_jobs`, `discovery_runs`, `account_tally_writes` | Add as a release-checklist line. |
| P7 | ≥ 2 sources or dependent schedules | **Self-hosted Airflow + Astronomer Cosmos** on a small VM | Not Cloud Composer. |
| P8 | P5 | **Looker Studio** on `marts`, read-only service account | Internal only. |

Production costs to verify at P2: BigQuery storage/query (expected ≈ free tier),
Datastream per-GB processed, Cloud Run Job runtime, Airflow VM when P7 arrives.

---

## Phase 6 — Customer analytics suite (designed, gated)

**Gate:** a written data policy and DPA covering customer business data
(ledgers, vouchers, bill amounts), the residency decision, and a tenant erasure
procedure. Until then, `config`, `result`, `plan`, `receipt`, `catalog`,
`observations`, `target`, `changes`, `input` and file content stay out of the
manifest.

**Design (D8: build pooled, serve bridged):**

```
raw → staging → intermediate → marts_customer        (pooled, tenant_id on every row)
                                     └─► tenant_<slug>.*   views only, one schema per tenant
marts_internal (Phase 3)  ── never exposed to customers
```

- **Generation:** a dbt `run-operation` (or post-hook) creates/updates one schema
  per analytics tenant with views `SELECT * FROM marts_customer.x WHERE tenant_id = '<uuid>'`.
  Adding a tenant is cheap; one dbt build serves all tenants.
- **Access:** one role per tenant, `USAGE` on its schema only.
  - Postgres: views run with the owner's privileges by default. Use
    `security_barrier` views so user functions cannot be pushed below the
    tenant filter, or `security_invoker` views (PG ≥ 15) over tables with
    row-level security policies on `tenant_id`.
  - BigQuery: dataset per tenant with authorized views, or row access policies.
- **Tests:** every `marts_customer` model has non-null `tenant_id`; every tenant
  view filters exactly one tenant (CI query over `pg_views`).
- **Erasure:** OLTP tenant deletion cascades, the warehouse does not. A tenant
  erasure job deletes the tenant's rows from every pooled layer, drops the
  tenant schema and role, and deletes the object-store prefix (0.4); it logs a
  receipt.
- **Upgrade path:** the per-tenant schema is the stable contract. An enterprise
  customer needing physical isolation gets real tables (or a separate
  dataset/project) behind the same names, with no change for them.
- **Serving layer:** many customers loading dashboards is a different workload
  from internal analysis. Evaluate BigQuery + BI Engine vs ClickHouse vs a
  Postgres serving database, and Superset for embedding.
- **Classification:** `industry` as a controlled lookup (consider a standard
  such as NAICS) and tenant `timezone` for local-day metrics.

---

## 12. Risk and failure-mode register

| # | Risk | Effect | Mitigation |
| --- | --- | --- | --- |
| R1 | Editing an applied migration | Production and dev migrations refuse to run | §0.0 rule; review checklist. |
| R2 | Commit-time skew on cursor loads (`now()` is transaction **start** time) | Rows committed late are skipped forever | Lookback window + idempotent merge; CDC in production. |
| R3 | Hard deletes invisible to cursors | Warehouse keeps rows the OLTP removed | Full refresh for mutable tables; `append_merge` only where keeping deleted rows is intended; CDC `_source_deleted` later. |
| R4 | Full refresh on a retention-deleted table | Warehouse history erased | Manifest marks such tables `append_merge` (0.5); CI test. |
| R5 | Cross-table inconsistency within one load | Intermittent relationship test failures | Single transaction, one fdw snapshot (1.3). |
| R6 | Secrets or personal data extracted | Leak through the warehouse | Column-level grants from the manifest; excluded tables; HMAC pseudonymisation; CI coverage test. |
| R7 | Schema drift (renamed/dropped column) | Broken models discovered late | CI builds the warehouse on every PR against freshly migrated OLTP. |
| R8 | Enum drift (new state added to a `CHECK`) | Metrics silently misclassify | `accepted_values` + constraint comparison test. |
| R9 | `mock-tenant` data in metrics | Wrong launch numbers | Mart-level filter, `tenants.kind`, test asserting no internal tenant in marts. |
| R10 | Trigger changes worker semantics | Queue order or lease reclaim changes | Phase 0.1 decouples columns first; tests for queue/lease behaviour. |
| R11 | Backfilled timestamps treated as exact | Misleading latency history | `created_at_is_backfilled` flag; exclude from latency metrics. |
| R12 | Replication slot abandoned (prod) | WAL fills disk, OLTP outage | Slot lag alert, `max_slot_wal_keep_size`, runbook. |
| R13 | fdw load stresses OLTP | Slow app | Locally irrelevant; in production extraction moves to CDC/replica, never fdw against the primary. |
| R14 | dbt dependency conflicts with the app | Broken lockfile | Standalone uv project (1.1). |
| R15 | Concurrent loads | Duplicate or partial data | Advisory lock. |
| R16 | Customer data enters before policy | Contract/legal exposure | Phase 6 gate; manifest exclusions reviewed in CI. |
| R17 | Cross-tenant leakage in customer views | Severe trust/legal incident | Barrier/invoker views + RLS, per-tenant roles, CI view-filter test. |
| R18 | Time-zone boundaries | "Daily" numbers off by a day for IST customers | Internal metrics in UTC (documented); tenant timezone before Phase 6. |
| R19 | JSON payload shape changes | Staging breaks or misparses | Unpack only documented fields, keyed by `definition_version`. |

## 13. Edge cases checklist

Verify each with a test or an explicit note before calling a phase done.

- Child runs (`parent_run_id`) are not double-counted in run metrics.
- Runs stopped by an operator (`error='Stopped by operator.'`) are distinguishable from genuine failures.
- A run retried via a new `request_key` counts as a new run; the same `request_key` never does.
- Attention items marked done and later re-raised under the same `event_key` (unique per tenant) are understood: does `done` → `pending` happen?
- Desktop jobs with many `attempts` and finally succeeded count as success with retries, not failure.
- Revoked or expired companion devices still attribute their historical jobs.
- Users who belong to several tenants appear once in `dim_users` and per tenant in `dim_memberships`.
- Users removed from a tenant (membership deleted) disappear from full-refresh `dim_memberships`; acceptable now, needs snapshots later.
- Tenant renamed (slug change): marts keyed by `tenant_id`, never slug, except the exclusion variable.
- Empty warehouse (fresh clone, no seed): `dbt build` succeeds with zero rows.
- Load interrupted mid-way: nothing committed, watermark unchanged, rerun succeeds.
- Clock differences between app containers: irrelevant because all timestamps come from the database `now()`.
- Rows created during a load: included next run (lookback) and never duplicated (merge by key).
- `account_runs` compatibility view: not extracted; base table `workflow_runs` only.

## 14. Open questions

| # | Question | Needed by | Default if unanswered |
| --- | --- | --- | --- |
| Q1 | Data residency: may analytics data be stored in `us-central1` like the OLTP, or must Indian customer data stay in India (DPDP Act)? | P2 | Same region as the OLTP. |
| Q2 | Exact definition of "automation rate" / "best-guess share" (denominator: bills scanned, bills written, or records?) | Phase 3 | Ship the model with the definition in YAML, mark it provisional. |
| Q3 | Retention for `workflow_run_diagnostics` in the OLTP | 0.5 follow-up | 30 days, like desktop diagnostics. |
| Q4 | Reporting time zone for internal metrics | Phase 3 | UTC. |
| Q5 | Which OpenAI usage/cost source (API export) becomes the second source? | P7 | None until then. |
| Q6 | Industry classification standard | Phase 6 | Controlled lookup, designed with the suite. |

---

## Appendix A — OLTP table inventory

Starting point for `extract/tables.yml` and for Phase 0 triggers. "Mutable" =
rows are updated after insert (gets `updated_at` + trigger in 0.1).

| Table | Extract | Mode | Excluded columns (reason) | Mutable | Phase 0 notes |
| --- | --- | --- | --- | --- | --- |
| `tenants` | yes | full | — | yes | `kind`, `updated_at` |
| `tenant_domains` | yes | full | — | yes (`verified_at`) | |
| `users` | yes | full | `password_hash` (secret); `email` → HMAC, `name` dropped in staging | yes | |
| `memberships` | yes | full | — | yes (role) | |
| `invitations` | yes | full | `token_hash` (secret); `email` → HMAC | yes | |
| `join_requests` | yes | full | — | yes | |
| `sessions` | **no** | — | authentication secrets | | |
| `email_verifications` | **no** | — | authentication secrets | | |
| `employees` | yes | full | `config_schema`, `config_values` (may hold customer settings; review in Phase 6) | yes | |
| `workflows` | yes | full | `config_schema`, `config_values`, `execution_binding` (review in Phase 6) | yes | |
| `workflow_employees` | yes | full | — | no | |
| `tasks` | yes | full | `title`, `summary` (free text may contain business data) | yes | |
| `task_events` | yes | append_merge (`created_at`) | `summary` (free text) | no | |
| `workflow_runs` | yes | full | `config`, `result`, `file_ids` (business), `session_id`, `turn_id`, `request_hash` | yes | `created_at`, `queued_at`, `heartbeat_at`, cleanup columns |
| `workflow_run_diagnostics` | yes | append_merge (`id`) | `details` until reviewed; `summary` free text | no | retention (Q3) |
| `hosted_environment_slots` | no (now) | — | coordination state | yes | revisit for cost analytics |
| `worker_wakeup` | **no** | — | process coordination | | |
| `event_outbox` | no (now) | — | `payload` is business data; no publisher yet | yes (`published_at`) | |
| `account_sources` | yes | full | `label` (customer folder names) | yes | |
| `account_files` | yes | full | `content` (bytes), `path` (customer paths) | yes (`current`) | 0.4 object store |
| `account_catalogs` | yes | full | `catalog` (business) | yes | `created_at`, `updated_at` |
| `account_writes` | yes | full | `content` (bytes), `changes` (business), `path` | yes | `created_at`; 0.4 |
| `account_tally_writes` | yes | full | `plan`, `receipt` (business), `identity`, `company` (customer names) | yes | |
| `attention_items` | yes | full | `target` (business), `identifier`, `label` (bill identifiers) | yes | `refreshed_at` |
| `attention_events` | yes | append_merge (`created_at`) | `summary` (free text) | no | |
| `desktop_devices` | yes | full | `token_hash` (secret), `installation_id`, `name` | yes | |
| `desktop_source_bindings` | yes | full | — | no | |
| `desktop_jobs` | yes | full | `input`, `result` (business), `claim_token` (secret), `request_hash`, `receipt_hash` | yes | |
| `desktop_job_requests` | no | — | idempotency bookkeeping | no | |
| `desktop_diagnostics` | yes | append_merge (`created_at`) | `payload` until reviewed | no | 30-day OLTP retention |
| `discovery_runs` | yes | full | `config`, `observations`, `catalog` (business), `request_hash`, `fingerprint` | yes | |

Free-text and identifier columns (`summary`, `label`, `identifier`, `company`)
are excluded conservatively: they can contain bill numbers, party names or
ledger names. Re-include them individually under the Phase 6 policy.
