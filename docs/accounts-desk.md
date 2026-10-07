# Accounts desk: Excel and Tally workflows

Source discovery and Bill entry execute through the shared tenant API, durable
PostgreSQL worker and OpenAI-hosted Agents API. All model calls use `gpt-6-luna`.
The existing `apps/solution-api/.env` key is reused by the API and worker; it is
never included in agent files or exposed to the browser.

## Product loop and ownership

1. Connect a local folder in Chrome/Edge, then select the relevant Excel files.
   Browser directory handles stay in IndexedDB. Only supported files from the
   chosen folder are synchronized, with immutable tenant-scoped provenance.
2. Source discovery uses the managed Codex harness to inspect actual workbooks,
   including headers below row 1, sheet contents and named tables. Codex proposes
   business meanings, purposes and record keys. Review uses searchable,
   collapsible mappings; confirmation creates a versioned catalog.
3. Launch Bill entry with multiple PDFs/images and the confirmed catalog.
   After setup, the dashboard runs saved file selections with tenant defaults in
   one click; workflow details expose configuration and per-run overrides.
   Codex recognizes the appropriate workbook/sheet/table from actual business
   context. No client filename, sheet name or invoice column schema is hardcoded
   in the executor. Ambiguous recognition becomes an unresolved review item and
   holds that bill while other bills continue. Confirmed concepts enable selected deterministic checks;
   missing reference evidence stays visible rather than implying reconciliation.
4. Review values, page evidence, findings and append/edit choice. Approval is
   required initially; tenant defaults and per-run options are editable.
5. The Excel adapter prepares only the approved destination edits. The browser
   checks the original hash, keeps a recovery copy, saves to the existing file,
   reads it back and submits a receipt. Only matching saved bytes complete the
   task. Users do not have to upload a workbook again or download a replacement.

Minkops owns authorization, immutable inputs, approvals, validation and safe
commits. OpenAI owns reasoning and its execution environment. This first web
version synchronizes selected bytes to the API and hosted session; it is not
fully local processing. The Windows companion implements the same approved
write contract for granted folders, including requests started from the web.
See [Windows setup and recovery](windows-app.md). MIN-118 provides confirmed
Tally discovery; [MIN-119 bill entry](bill-entry.md) adds reviewed Purchase
vouchers, duplicate alerts, correction handoff and exact destination readback.

## Run contracts and recovery

Each run pins definition version, instructions, `agent-output.schema.json`,
configuration, input hashes and confirmed mappings. The agent's JSON artifact
is accepted only from the completed turn and exact output path. Agent schemas
describe structure, not business field names. The older `output.schema.json`
and platform `validate_output` describe a separate final-report envelope; they
are not substituted for the agent proposal contract used by this runtime.

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

Local writes reserve each workbook, reject duplicates and changed local files,
and serialize same-browser tabs. A disconnected receipt can be retried: an
already matching workbook is verified without appending again. Unverified
recovery copies remain in IndexedDB; verified writes remove them. Cancel
remaining saves releases reservations, retains audit records, and does not
undo changes already saved. A late valid receipt is recorded without converting
a cancelled run into success. External workbook changes require rediscovery;
Minkops' own verified writes can advance the confirmed catalog safely.

## Local setup

From the repository root, use an isolated development database. Do not reset a
database whose migration checksum differs; investigate or create a new one.

```sh
docker compose -f infra/compose.yml up -d app_db
export DATABASE_URL=postgresql://minkops:minkops-local@127.0.0.1:5433/minkops_accounts_demo
uv sync --all-packages
uv run --all-packages python db/migrate.py
uv run --all-packages python db/seed_demo.py
uv run --all-packages --with pymupdf python scripts/prepare_accounts_demo.py
AUTH_DEV_MODE=1 uv run --all-packages uvicorn minkops_api.main:app --host 127.0.0.1 --port 8000
```

Create that database first if it does not exist. In another terminal with the
same DATABASE_URL, run `uv run --all-packages python -m minkops_api.accounts_worker`.
Start the existing Vite app in `apps/solution-web` (`npm run dev`, port 3000).
Sign in at `/login` with `demo@example.com` and the seed's printed
password. The seed activates these two workflows only for the mock tenant and
preserves existing operator settings and paused workflows.

Connect `apps/solution-api/data/mock-workspace`, select its three reference
workbooks for discovery, and confirm the register as a destination. The sample
register's `record_id` can be confirmed as `entry_id` for application-generated
IDs; this is an explicit mapping, not an assumption made for all tenants.
Select the three PDFs and PNG for a mixed Bill entry run. The preparation script
refuses to replace an existing workspace and never modifies source samples.

## Supported scope and verification

The adapter supports ordinary `.xlsx` sheets and named tables without totals.
It preserves unrelated cells, copied styles and translated formulas, but does
not calculate formulas. Macro, pivot, slicer, ActiveX, external-link and protected
destinations require additional adapters. Table expansion into occupied cells
is rejected. Browser permissions and an open Chrome/Edge page are required for
local saves; hosted extraction continues while the page is closed.

Sources are limited to 100 supported files, 5 MB per file and 30 MB per refresh.
Runs allow up to 45 files and 8 MB including workbook references; hosted uploads
also enforce provider limits. Manual uploads work for bill inputs and reference
inspection; writable destinations require a connected folder.

Offline tests replace only the paid agent boundary and cover real database/auth,
tenant isolation, approval, cancellation, receipt replay, schema validation,
safe workbook updates and local commit conflicts. Run API tests with
TEST_DATABASE_URL pointing to a migrated, demo-seeded test database. Browser
verification also ran the real hosted model: discovery found headers on row 4;
three PDFs plus a scanned PNG appended four rows to the existing local register
(16 → 20), preserved prior rows and reference files, and completed only after a
verified browser receipt. This is local proof; no production deployment is implied.

Database-backed pytest runs now create and clean up their own database; see
[isolated integration tests](../db/README.md#isolated-integration-tests). The
supplied PostgreSQL role needs database-creation permission.
