# Production deployment and MIN-123 closeout

Prepared 7 October 2026. Target: **CAD 15/month for Minkops GCP hosting**, including
product and corporate website. OpenAI usage is separate. This is a plan; the new
product backend has not been deployed.

## Observed account and recommended topology

Read-only authenticated inspection found minkowski-web-prod (four Cloud Run
services, no VMs) and myndral-prod (five services, three jobs) on the open CAD
billing account. Myndral uses PostgreSQL 16 myndral-db in us-central1:
db-f1-micro, zonal, 10 GB SSD. minkops-interest-api already runs there; the
corporate frontend remains on Vercel. No cloud configuration or DNS was changed.
Local gcloud 588.0.0, uv and Firebase CLI 15.32.1 are installed.

Use the same managed pattern as Myndral:

"Myndral-like" means replicating its service pattern and modest database scale.
Sharing its SQL instance is an optional cost-saving recommendation, not a user
requirement. A dedicated small SQL instance remains a valid option if actual CAD
prices and measured variable usage leave room below the agreed monthly ceiling.

| Component | Initial setting |
| --- | --- |
| Website and console | Two static Firebase Hosting sites; existing Vite builds |
| Product API | Cloud Run request billing, min 0/max 1, 1 CPU, 512 MiB, concurrency 8 |
| Website interest API | Existing service if same project; otherwise redeploy it in Hosting project |
| Worker | On-demand bounded Cloud Run Job; one task, parallelism 1, 1 CPU/512 MiB |
| Database | Separate Minkops DB and role on existing instance, only after capacity/recovery gates |
| Definitions | Immutable image with core employees and additive client variants |
| Credentials | Dedicated service accounts, Secret Manager, Cloud SQL connector; CI workload identity |

Prefer a dedicated Minkops project for IAM/cost separation, sharing SQL only if
safe; cross-project SQL needs explicit connector IAM. Firebase rewrites require
Cloud Run in the Hosting project, so redeploy the existing interest API there.
Alternatively use myndral-prod with separate sites/services/roles. Select the
project before provisioning; do not silently change Myndral settings.

infra/solution.Dockerfile builds locked Python dependencies and repository
definitions, running as a non-root user. infra/firebase.json supplies two Hosting
routing templates; project/site targets still need assignment. API rewrites and
SPA fallbacks are specified. No project or site has been created.

## Cost envelope and SQL gate

Illustrative conversion: **CAD 1.40/USD**, not a live exchange-rate guarantee.
Confirm actual CAD SKUs, taxes and current-month usage before deployment.
Myndral's existing bill is separate from Minkops's incremental budget; fully
allocated reporting must include a stated share of the SQL baseline.

| Scenario | Planning estimate |
| --- | --- |
| Shared SQL, small pilot | Target CAD 3–8 incremental/month, retaining budget margin |
| New db-f1-micro + 10 GB SSD | About USD 9.37/CAD 13.12 per 730-hour month before backup/other charges; viable only with a verified very small variable-cost envelope |
| Eligible free e2-micro + self-managed PostgreSQL | USD 3.65/CAD 5.11 public IPv4 baseline; plan CAD 6–10 with small backup/transfer, operational ownership required |
| Continuous Cloud Run worker | Exceeds budget; do not deploy the current forever loop as always-on |

Free Cloud Run allocations are shared across projects on the billing account.
Existing Myndral jobs already run regularly; album email had 253 executions.
Do not assume an unused free pool. With no free allocation, 1,000 executions of
60 seconds at 1 CPU/512 MiB cost about USD 1.14/CAD 1.60; three-minute executions
cost about CAD 4.79. API runtime, images, logging, backups and outbound bytes add
to this. Jobs have a one-minute billing minimum; minutely empty polling is costly.

Firebase static Hosting includes 10 GB storage and 10 GB/month transfer; excess
transfer costs USD 0.15/GB. API rewrites add Cloud Run usage. Choose static Hosting
rather than App Hosting, paid HTTPS load balancers, Cloud NAT, Redis, Kubernetes
or HA SQL. The VM fallback depends on free-tier eligibility and supported US
regions; it is self-managed, lacks HA and needs residency/latency review.

Seven-day SQL hourly maxima: CPU ~16.6%, used data ~77 MiB, PostgreSQL backends
up to seven **per reported series**. Memory utilization reported 100%; this
alone does not distinguish cache from working memory. Inspect free/cache/usage
and total connections, then load-test before sharing. Low CPU is not proof of
spare memory. Backups and deletion protection are disabled: verify recovery before
launch. Use a separate database/role, bounded connections and no Myndral credentials.

Set project-scoped CAD alerts at 5/10/13 and halt new workload at projected 15.
Use a supported billing spend cap if available; verify service coverage and
enforcement delay. Alerts and instance limits alone cannot guarantee a ceiling.
Bound images/log retention and storage growth. Current billing budgets could not
be verified because of the read-only quota-project setup.

## Ordered implementation and deployment

1. **Adapt worker hosting before launch.** Current bootstrap runs forever.
   Add a bounded drain preserving claims, hosted-session recovery, cleanup and
   native-write reconciliation across exits. Enqueue coalesced durable wake-up
   transactionally with runnable work; dispatch after commit, retry failed
   dispatch and use a low-frequency recovery sweep. Include desktop receipts,
   retries and cleanup triggers. Existing database locks prevent duplicate paid
   calls. Test lost wake-up, crashes, timeout and no-work exit. This adaptation
   is not implemented by the Source Discovery patch.
2. **Confirm SQL/budget gates.** Inspect memory components and concurrency;
   isolate DB/role; enable backups/protection under a reviewed change; prove
   restore into an isolated DB and compare projected spend. If sharing is unsafe,
   choose the bounded VM alternative or revise capacity/budget before provisioning.
3. **Bootstrap production.** Select project, accounts/sites and workload identity;
   create app secrets, verified admin/tenant membership and email delivery.
   Set AUTH_DEV_MODE=0; never demo-seed production. Stop workers, migrate through
   0012_schema_discovery and install trusted client bindings. Reinstall legacy
   bindings to record the owning solution identity.
4. **Deploy versioned image.** Run migrations/installation with controlled
   credentials; deploy API and bounded worker with Cloud SQL connector.
   Existing immutable file snapshots live in PostgreSQL: include their growth
   in backups/capacity. Container disk is temporary. Add object storage only for
   a measured retention need with matching ownership/transport tests.
5. **Deploy both static builds.** Build console and corporate site from reviewed
   revision; set corporate VITE_INTEREST_API_URL=/api/interest. Bind Hosting
   targets. Verify API proxy, tenant isolation, CSRF, logout, email/password
   flows and private,no-store caching. App sessions use __session, the cookie
   Hosting forwards; this is not Firebase Auth.
6. **Prove live operation.** Run controlled hosted workflows; verify offline-PC
   waiting/resume, schema review, current references, approve/hold/reject/edit,
   replay-safe readback and paid-environment cleanup. Measure job durations,
   connections, usage and errors before accepting customer workload.

## Corporate website: retire Vercel

Inventory Vercel domains/redirects, environment variables, analytics and any
non-repository functions. Deploy corporate Vite build to Firebase Hosting;
verify routes, assets, themes, SEO metadata and interest delivery on its temporary
URL. Preserve existing interest API validation/delivery and email credentials.

Attach the corporate custom domain and managed HTTPS, then change required DNS
only; preserve mail/MX/TXT records. Verify apex/www redirects, HTTPS, deep-link
refresh and a real interest submission outside the developer machine. Retain
Vercel through DNS propagation and an agreed observation window. Once verified,
remove its Git integration, credentials, project and paid plan. Replace its
required CI checks with repository validation and explicit GCP deployment gates.
Record rollback DNS, last-good image and Hosting release before removal.
No Vercel or DNS changes were made during planning.

## MIN-123 completion gates

Merge readiness and production release are separate. Close MIN-123 only after
backend/website availability, worker wake/recovery, restored backup, budget
controls, ownership and rollback are proved. Verify the issue's exact current
acceptance text before updating status; this document does not close the issue.

The current [MIN-123 description](https://linear.app/minkops/issue/MIN-123/deployment)
also requires sweeping MIN-122, publishing the finalized installer for download
on the marketing website, thorough manual testing and demo preparation. After
production checks, publish a versioned 0.4.0 installer with checksum and release
notes to a durable GCP download location; verify the website link on a fresh PC.
Prepare an isolated demo tenant/account and synthetic fixtures, prove both Source
Discovery and Bill Entry end to end, and record the meeting/demo checklist.
Store release may wait. Do not seed synthetic data into customer tenants.

MIN-122 still needs clean Windows 10/11 x64 and production HTTPS verification.
Rebuild companion 0.4.0; cover driver-present/missing, server-backed data through
local Tally, offline/revoked PC, refreshed folder grant and JSON download.
Repeat new header-only discovery and a reviewed hosted Tally/Excel write.
Confirm signing/distribution expectations before external release.
Historical RC/current-PC tests do not satisfy the fresh-PC matrix.
Scheduling MIN-121 remains separate unless required by MIN-123 acceptance.

## Official references

- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- [Hosting quotas](https://firebase.google.com/docs/hosting/usage-quotas-pricing)
- [Hosting/Cloud Run routing](https://firebase.google.com/docs/hosting/cloud-run)
- [Hosting cookies/cache](https://firebase.google.com/docs/hosting/manage-cache)
- [SQL memory diagnosis](https://docs.cloud.google.com/sql/docs/postgres/optimize-high-memory-usage)
- [Free-tier eligibility](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [External IP pricing](https://cloud.google.com/vpc/network-pricing)
- [Billing spend caps](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
