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
Cloud Run Job. Transactional generations coalesce immediate wakes and an hourly
Scheduler recovers lost dispatches. Hosting sites are assigned by the explicit
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
| Worker | Cloud Run Job `minkops-worker`: one task, one lane, no retries, 1 CPU / 512 MiB; the 60-minute task timeout leaves the 45-minute active-processing budget time to stop and reconcile |
| Recovery | Scheduler `minkops-worker-recovery`: hourly, ops identity, no retries |
| Database | Isolated `minkops` PostgreSQL 16 database on the shared Cloud SQL instance `myndral-prod:us-central1:myndral-db` |

Each service has its own service account and per-secret IAM. Only the two public
HTTP services disable the Cloud Run invoker check; the application still enforces
sessions, tenants and CSRF. The worker Job stays IAM-private. Production sets
`AUTH_DEV_MODE=0` and secure cookies, and API responses are private, no-store.

Database roles are separate from Myndral's: runtime `minkops_app` (16 connections,
no DDL), `minkops_owner` (NOLOGIN, owns the schema) and `minkops_migrate`
(migrations only). Test a restore by loading a logical backup into a new
disposable database with `verify_database_restore.py`, using PostgreSQL 16 client
tools to match production; never restore over the shared instance as a test.

Cost controls: a CAD 15/month project budget alerts at 50%, 80% and 100%, and a
CAD 10/month Cloud Run spend cap applies to Cloud Run only, after an enforcement
delay. Neither is a universal hard stop; check actual spend before larger
rollouts. `artifact-cleanup.json` deletes builds older than 30 days and keeps
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
