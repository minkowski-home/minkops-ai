# Infrastructure

Python tools here provision, configure, deploy, audit and recover hosting/cloud
resources. `google_api.py` is their shared operator-only client, outside the app
image. Keep workflow and demo operations out of here: a workspace, the demo's
included, is created with `python -m minkops_api.install_workflows`, which has
separate responsibilities from cloud infrastructure and must remain opt-in.

`compose.yml` runs the local OLTP PostgreSQL database. The API and durable
Accounts worker are separate processes sharing that database. Sessions run on
OpenAI's Agents API with no hosted environment; Compose runs no AI executor.

Accounts desk runs one Agents API tool session per run item, with `gpt-6-luna`
and no hosted environment: a bill's pages arrive as images and text, and the
session calls Minkops's read-only tools and `propose`. API credentials stay outside
agent-readable content. A session is deleted once its usage is recorded; its tool
calls and IDs stay for audit.

The browser reads selected input files through a granted local folder. This is
a web adapter with synchronized snapshots, not fully local desktop execution.
The registered Windows companion syncs the Tally books read-only, and saves and
reconciles approved Tally writes. Business reasoning stays in the model's sessions;
no customer-machine executor is planned.

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
[Agents API guide](https://developers.openai.com/api/docs/guides/agents-api/overview).

## Production

Project `minkops-ai-prod`, region `us-central1`. The scripts here are the source
of truth for these settings; the table summarises them.

| Component | Configuration |
| --- | --- |
| Corporate site | Firebase Hosting `minkops-ai-prod`: minkops.com, www redirects to the apex |
| Console | Firebase Hosting `minkops-ai-console`: app.minkops.com |
| API | Cloud Run `minkops-solution-api`: min 0 / max 1, 1 CPU / 1 GiB, concurrency 2 (native evidence validation plus independent presence), 60 s |
| Interest form | Cloud Run `minkops-interest-api`: min 0 / max 1, 1 CPU / 512 MiB, concurrency 8, 30 s |
| Worker | Cloud Run Job `minkops-worker`: one task, twelve bounded lanes, no retries, 1 CPU / 1 GiB; the 60-minute task timeout leaves the 45-minute active-processing budget time to stop and reconcile |
| Recovery service | IAM-private Cloud Run `minkops-operations`: min 0 / max 1, 1 CPU / 256 MiB, concurrency 1, runtime database secret only, 60 s |
| Recovery schedule | Scheduler `minkops-worker-recovery`: every five minutes, OIDC using ops identity, service URL audience, no retries; calls `/reconcile`, never the raw worker-job API |
| Database | `minkops` PostgreSQL 16 database on Minkops' own Cloud SQL instance `minkops-ai-prod:us-central1:minkops-books`, created at the [cut-over](../docs/rebuild/cutover.md); the runtime connects through the `minkops-books-database-url` secret |

Each service has its own service account and per-secret IAM. Only the two public
HTTP services disable the Cloud Run invoker check; the application still enforces
sessions, tenants and CSRF. The worker Job and recovery service stay IAM-private.
The recovery deployment explicitly enables invoker IAM, removes public service
principals and grants its scheduler identity scoped service invocation. Its
database connection uses the runtime role, and it receives no model key.
Production sets
`AUTH_DEV_MODE=0` and secure cookies, and API responses are private, no-store.

The instance (PostgreSQL 16, zonal, encrypted connections only, daily backups
with point-in-time recovery, deletion protection) isolates client books,
including the Tally mirror, from other products and gives the worker lanes
connection headroom; it is not a speed fix. Create it once with
`provision_database.py --create-instance --tier <tier>`: the tier is the
operator's recorded cost decision. The cut-over on 23 October 2026 created it at
`db-f1-micro`, the tier of Myndral's instance, as the owner chose. Until then,
production ran the pre-rebuild build on Myndral's shared instance
`myndral-prod:us-central1:myndral-db`. The cut-over retired that build for good:
one final logical backup is kept off-site, and its database, roles and secrets
left that instance, whose other contents stay Myndral's.

Database roles: runtime `minkops_app` (16 connections, no DDL), `minkops_owner`
(NOLOGIN, owns the schema) and `minkops_migrate` (migrations only). Test a restore
by loading a logical backup into a new disposable database with
`verify_database_restore.py`, using PostgreSQL 16 client tools to match
production; never restore over a live database as a test.

Cost envelope: **CAD 20/month**, set while Minkops shared Myndral's instance:
CAD 8 for half that fixed SQL footprint, a CAD 10 target for Minkops-exclusive
resources, and CAD 2 of contingency. Since the cut-over, `minkops-books` is
Minkops' alone and bills to `minkops-ai-prod`: a 31-day month costs about
CAD 13.48 before backups and network, 744 hours at CAD 0.014874825/hour plus
10 GiB at CAD 0.2408305/GiB-month (the Google catalog's CAD rates on 21 October
2026). The envelope, and the CAD 10 project alert below, which now counts the
instance, wait on the owner's revision. Review FX, backups, storage growth and
actual billing monthly. A second SQL instance is not provisioned merely to bypass
inefficient queries; benchmark the corrected paths first.

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
the three newest versions, the rollback for a bad release. Hosting retains two releases per site and logs are kept for 30 days.

### Operator deployment

Deployments run as the authenticated owner with in-memory gcloud tokens; there
are no service-account keys. Use `uv sync --frozen --all-packages`, Node 24 with
`npm ci`, gcloud, Docker and the Cloud SQL Auth Proxy.

1. `bootstrap_hosting.py` creates the budgets and Hosting sites (initial setup).
2. `provision_database.py --sql-project minkops-ai-prod --instance minkops-books
   --state-dir DIR --create-instance --tier <tier>` creates the dedicated instance
   once. Then, through a loopback proxy to it, the same command without
   `--create-instance` creates roles, the database, migrations and runtime grants
   (initial setup), and `verify_database_restore.py` with the same three flags
   proves a restore. DIR is a private directory holding the instance's credentials.
   Both commands reach the proxy on 127.0.0.1 at `--proxy-port` (5433 by default).
   The restore check runs PostgreSQL 16's `pg_dump` and `pg_restore` from
   `--pg-bindir`, or else from `PATH`, and refuses any other major version.
   `provision_database.py` applies `db/migrations`, so it runs with the repository
   root on `PYTHONPATH`. The [cut-over](../docs/rebuild/cutover.md) gives each
   command in full.
3. `configure_runtime.py --state-dir DIR` sets named Secret Manager versions and
   scoped IAM. Rotate a secret by adding a version and updating every deployment's
   reference to it.
4. Build images with local Docker, as above, and push them tagged with a reviewed
   commit: Cloud Build's default service account here cannot read its source
   bucket, an IAM change that waits on the owner. Record the previous revision,
   then run `deploy_runtime.py --image ... --interest-image ...`. Check Ready,
   traffic and Job success rather than only gcloud's exit status.
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
