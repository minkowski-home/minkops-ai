# Accounts desk workflows

Source discovery, Bill entry and Statement entry execute through the shared
tenant API, durable PostgreSQL worker and OpenAI-hosted Agents API. All model calls use `gpt-6-luna`.
The existing `apps/solution-api/.env` key is reused by the API and worker; it is
never included in agent files or exposed to the browser.

## Product loop and ownership

1. Connect a local folder in Chrome/Edge, then select the relevant files.
   Browser directory handles stay in IndexedDB. Only supported files from the
   chosen folder are synchronized, with immutable tenant-scoped provenance.
2. Source discovery collects workbook sheet/header/table definitions and formula
   text through the connected PC. Fresh workbook projections exclude business
   rows and cached results. The managed Codex harness proposes business meanings,
   purposes and record keys from this structure; unclear headers require review.
   For Tally, it collects all loaded companies' undated masters and detailed
   vouchers for the selected inclusive period. Hosted interpretation proposes
   only evidenced obscure conventions and exceptions. Confirmation creates a
   versioned client-context package; see [Source Discovery](source-discovery.md).
3. Launch Bill entry with multiple PDFs/images and the confirmed catalog.
   After setup, the dashboard runs saved file selections with tenant defaults in
   one click; workflow details expose configuration and per-run overrides.
   Bill runs pin a complete, confirmed version 2 package and either lock a
   company or infer it from buyer evidence. Codex proposes the client's own
   voucher from that context and the bill; no ledger, voucher type or field list
   is hardcoded in the executor. Ambiguous recognition becomes an unresolved
   review item and holds that bill while other bills continue.
4. Review bill identifiers and concise status with one-click decisions.
   Accounting entry/corrections happen in original systems; no values, correction
   prompts or operation choices are editable in Minkops. Members can change
   per-run options; only admins change saved tenant/employee defaults.
5. The Windows companion saves each approved voucher natively in Tally, reads it
   back and submits a receipt. Only a verified readback completes the bill.

Minkops owns authorization, immutable inputs, approvals, validation and safe
commits. OpenAI owns reasoning and its execution environment. This first web
version synchronizes selected bytes to the API and hosted session; it is not
fully local processing. The Windows companion performs every approved native
write, including those approved from the web.
See [Windows setup and recovery](windows-app.md). [Source discovery](source-discovery.md)
provides confirmed Tally context; [Bill entry](bill-entry.md) and
[Statement entry](statement-entry.md) add reviewed native vouchers, duplicate
alerts, correction handoff and exact destination readback.

## Run contracts and recovery

Each run pins definition version, instructions, `agent-output.schema.json`,
configuration, input hashes and confirmed mappings. The agent's JSON artifact
is accepted only from the completed turn and exact output path. Agent schemas
describe structure, not business field names. Each definition still declares
the descriptor's `output.schema.json`, but Accounts validates only the pinned
agent proposal schema and its business checks.

New runs additionally pin the complete hosted execution bundle: SKILL.md,
execution-instructions.md, workflow/configuration/output contracts, declared
supporting scripts/references, model, packages, artifact path, and content
digest. Runtime execution uses the pinned bundle even if checkout files change.
Launch idempotency, worker recovery, raw-proposal persistence, and cleanup are
shared platform controls; Accounts retains catalog, evidence, business, approval,
and destination-write semantics. The hosted executor remains shared.
Legacy queued runs without a complete bundle require explicit relaunch; saved
active sessions can still be reconciled without replaying input.

The worker stores session/turn IDs as events arrive, holds an advisory lock and
reconciles the existing session after a restart. An ambiguous creation without
a persisted ID fails visibly rather than blindly replaying a charged request.
Hosted environments are released after durable results; idle workers retry
pending cleanup. Audit IDs and results stay in PostgreSQL.

Tally writes reserve each company and bill identity, so two runs cannot save the
same bill at once. A retried save reads Tally first: a voucher that was already
saved is verified rather than entered twice. Stopping the task cancels unsaved
writes, releases their reservations, keeps unsaved bills in Attention and records
the actor; it does not undo vouchers already saved. A late valid receipt is
recorded without converting a stopped run into success. Held bills are rechecked
or deferred only through Attention decisions.

## Local setup

From the repository root, use an isolated development database. Do not reset a
database whose migration checksum differs; investigate or create a new one.

```sh
docker compose -f infra/compose.yml up -d app_db
export DATABASE_URL=postgresql://minkops:minkops-local@127.0.0.1:5433/minkops_accounts_demo
uv sync --all-packages
uv run --all-packages python db/migrate.py
uv run --all-packages python db/seed_demo.py
AUTH_DEV_MODE=1 uv run --all-packages uvicorn minkops_api.main:app --host 127.0.0.1 --port 8000
```

Create that database first if it does not exist. In another terminal with the
same DATABASE_URL, run `uv run --all-packages python -m minkops_api.accounts_worker`.
Start the existing Vite app in `apps/solution-web` (`npm run dev`, port 3000).
Sign in at `/login` with `demo@example.com` and the seed's printed
password. The seed installs the mock-client composition (Source discovery,
Statement entry and Bill entry) for the mock tenant and preserves existing
operator settings and paused workflows.

The mock client's workflow policy enables Tally only, so discovery and saves
need the [Windows companion](windows-app.md) connected to a PC with the test
companies open in Tally. The [five-company rehearsal](tally-rehearsal.md) seeds
synthetic companies and bills for that.

## Supported scope and verification

Source discovery reads ordinary `.xlsx` sheets and named tables; Minkops never
edits a workbook. Browser folder refreshes need permission and an open
Chrome/Edge page; hosted extraction continues while the page is closed.

Sources are limited to 100 supported files, 5 MB per file and 30 MB per refresh.
Runs allow up to 45 files and 8 MB including discovery workbooks, full Tally
lookup files and bills; individual lookup files are limited to 4 MB. Oversized
complete native discovery remains saved but visibly partial for hosted
interpretation, blocking dependent workflows. Hosted uploads
also enforce provider limits. Manual uploads work for bill inputs and reference
inspection.

Offline tests replace only the paid agent boundary and cover real database/auth,
tenant isolation, approval, cancellation, receipt replay, schema validation and
write reservations. Run API tests with TEST_DATABASE_URL pointing to a PostgreSQL
server role with database-creation permission; pytest creates and seeds its own
isolated database.

Database-backed pytest runs now create and clean up their own database; see
[isolated integration tests](../db/README.md#isolated-integration-tests). The
supplied PostgreSQL role needs database-creation permission.
