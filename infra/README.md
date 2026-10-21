# Infrastructure

Python tools here provision, configure, deploy, audit and recover hosting/cloud
resources. `google_api.py` is their shared operator-only client, outside the app
image. Keep workflow/demo operations in `scripts/`: `provision_demo.py` prepares
the verified demo owner and installation; `verify_production.py` checks the
reviewed synthetic bill lifecycle. These have separate responsibilities from
cloud infrastructure and must remain opt-in.

`compose.yml` runs the local OLTP PostgreSQL database. The API and durable
Accounts worker are separate processes sharing that database. OpenAI provisions
the agent execution environment; Compose does not run a Codex executor.

Accounts desk creates per-run `openai_hosted` Agents API sessions with
`gpt-6-luna`, network access disabled, and required Python packages. Selected
files are supplied as tenant-scoped immutable snapshots. API credentials stay
outside agent-readable content. Results are persisted before hosted environment
cleanup; workers retry pending cleanup and retain session IDs for audit.

The browser applies approved Excel writes through a granted local folder. This
is a web adapter with synchronized snapshots, not fully local desktop execution.
The registered Windows companion also reads schema metadata and reconciles
approved Tally writes. Business reasoning remains in OpenAI-hosted environments;
no customer-machine Codex executor is planned.

Build the production API image from the repository root:

```sh
docker build -f infra/solution.Dockerfile -t minkops-solution:review .
docker run --rm minkops-solution:review python -m minkops_api.install_workflows mock-client --validate-only
```

The same image runs `python -m minkops_api.accounts_worker --drain` as a bounded
Cloud Run Job. Transactional generations coalesce immediate wakes and a five-minute
Scheduler calls an IAM-private recovery service. It checks durable eligibility
before dispatching; idle ticks do not start worker executions. Hosting sites are assigned by the explicit
operator deploy script. Audit scripts read resource metadata/metrics without
retrieving secrets or customer database rows.

See [Accounts desk setup and limits](../docs/accounts-desk.md) and OpenAI's
[hosted environment guide](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted).

## Production

Project `minkops-ai-prod`, region `us-central1`. The scripts here are the source
of truth for these settings; the table summarises them.

| Component | Configuration |
| --- | --- |
| Corporate site | Firebase Hosting `minkops-ai-prod`: minkops.com, www redirects to the apex |
| Console | Firebase Hosting `minkops-ai-console`: app.minkops.com |
| API | Cloud Run `minkops-solution-api`: min 0 / max 1, 1 CPU / 512 MiB, concurrency 2 (Argon2 verification memory), 60 s |
| Interest form | Cloud Run `minkops-interest-api`: min 0 / max 1, 1 CPU / 512 MiB, concurrency 8, 30 s |
| Worker | Cloud Run Job `minkops-worker`: one task, four bounded lanes, no retries, 1 CPU / 512 MiB; the 60-minute task timeout leaves the 45-minute active-processing budget time to stop and reconcile |
| Recovery service | IAM-private Cloud Run `minkops-operations`: min 0 / max 1, 1 CPU / 256 MiB, concurrency 1, runtime database secret only, 60 s |
| Recovery schedule | Scheduler `minkops-worker-recovery`: every five minutes, OIDC using ops identity, service URL audience, no retries; calls `/reconcile`, never the raw worker-job API |
| Database | Isolated `minkops` PostgreSQL 16 database on the shared Cloud SQL instance `myndral-prod:us-central1:myndral-db` |

Each service has its own service account and per-secret IAM. Only the two public
HTTP services disable the Cloud Run invoker check; the application still enforces
sessions, tenants and CSRF. The worker Job and recovery service stay IAM-private.
The recovery deployment explicitly enables invoker IAM, removes public service
principals and grants its scheduler identity scoped service invocation. Its
database connection uses the runtime role, and it receives no model key.
Production sets
`AUTH_DEV_MODE=0` and secure cookies, and API responses are private, no-store.

Database roles are separate from Myndral's: runtime `minkops_app` (16 connections,
no DDL), `minkops_owner` (NOLOGIN, owns the schema) and `minkops_migrate`
(migrations only). Test a restore by loading a logical backup into a new
disposable database with `verify_database_restore.py`, using PostgreSQL 16 client
tools to match production; never restore over the shared instance as a test.

Cost envelope: **CAD 20/month including Minkops' share of shared SQL**. Reserve
CAD 8 for half the fixed SQL footprint (two products share it), target CAD 10 for
Minkops-exclusive resources, and retain CAD 2 of contingency. The current
31-day base SQL allocation is about CAD 6.74 before allocated backups/network:
half of 744 hours at CAD 0.014874825/hour plus 10 GiB at CAD 0.2408305/GiB-month.
These are the Google catalog's CAD rates on 21 October 2026; review allocation,
FX, backups, storage growth and actual billing monthly. Myndral's other charges
are outside the Minkops envelope. A second SQL instance is not provisioned merely
to bypass inefficient queries; benchmark the corrected paths first.

`bootstrap_hosting.py` updates the existing project alert to CAD 10 and the
Cloud Run-only gross spend cap to CAD 6, leaving room for Hosting, artifacts,
secrets and logs inside the exclusive target. Project alerts trigger at 50%,
80% and 100%. The recovery check does not start idle worker jobs. These controls
are conservative operating limits, **not a provider-guaranteed CAD 20 hard stop**:
Google's spend-cap enforcement is delayed, excludes persistent SQL/storage, and
the Budgets API does not expose actual accrued spend. Before paid rollouts,
check the billing report and retain the contingency; do not silently increase a
limit or purchase more capacity when it would breach this envelope. See
[Google spend-cap limitations](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
and [Cloud SQL pricing](https://cloud.google.com/sql/pricing).
`artifact-cleanup.json` deletes builds older than 30 days and keeps
the three newest versions; Hosting retains two releases per site and logs are
kept for 30 days.

### Operator deployment

Deployments run as the authenticated owner with in-memory gcloud tokens; there
are no service-account keys. Use `uv sync --frozen --all-packages`, Node 24 with
`npm ci`, gcloud, Docker and the Cloud SQL Auth Proxy.

1. `bootstrap_hosting.py` creates the budgets and Hosting sites (initial setup).
2. `provision_database.py` through a loopback proxy creates roles, the database,
   migrations and runtime grants (initial setup), then `verify_database_restore.py`.
3. `configure_runtime.py` sets named Secret Manager versions and scoped IAM. Rotate
   a secret by adding a version and updating both the API and worker references.
4. Build and push images tagged with a reviewed commit, record the previous
   revision, then run `deploy_runtime.py --image ... --interest-image ...`. Check
   Ready, traffic and Job success rather than only gcloud's exit status.
5. Build the corporate site with `VITE_INTEREST_API_URL=/api/interest` and the
   console, then `deploy_hosting.py corporate --installer PATH` (it verifies the
   installer's checked-in size and SHA before releasing it with the site) and
   deploy the console separately. `configure_domains.py` reports required DNS records.
6. `configure_retention.py` reapplies bounded retention; keep rollback artifacts
   before reducing it.

Roll back by restoring the previous Firebase Hosting release or Cloud Run
revision; never reverse a database migration to recover an application revision.
An unattended pipeline must use repository- and branch-bound OIDC Workload
Identity with an explicit production approval environment.
