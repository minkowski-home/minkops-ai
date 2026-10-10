# Production deployment and MIN-123 closeout

Executed 7–8 October 2026. Target: **CAD 15/month incremental Minkops GCP hosting**,
including the product and corporate website. OpenAI usage and Myndral's existing
bill are separate. Deployment availability does not close every MIN-123 gate.

## Deployed topology

Dedicated project `minkops-ai-prod` (791824186738), CAD billing account
`01CA76-B60F26-EF46E3`, region `us-central1`.

| Component | Deployed configuration |
| --- | --- |
| Corporate site | Firebase Hosting `minkops-ai-prod`; minkops.com, www redirect to apex |
| Console | Firebase Hosting `minkops-ai-console`; app.minkops.com |
| API | `minkops-solution-api`, request billing, min 0/max 1, 1 CPU/512 MiB, concurrency 2 |
| Interest form | `minkops-interest-api`, min 0/max 1, 1 CPU/512 MiB, concurrency 8 |
| Worker | `minkops-worker` Cloud Run Job, one task/parallelism 1, max retries 0, 1 CPU/512 MiB, 30-minute timeout |
| Recovery | `minkops-worker-recovery` Scheduler, hourly, OAuth ops identity, no retry storm |
| Database | Isolated `minkops` PostgreSQL 16 database on `myndral-prod:us-central1:myndral-db` |
| Credentials | Separate API/worker/ops/interest service accounts, per-secret IAM, Cloud SQL connector |

Temporary verification URLs: https://minkops-ai-prod.web.app and
https://minkops-ai-console.web.app. Native release profile uses
https://app.minkops.com. HTTPS is verified on all three custom hosts, including
the www-to-apex redirect and console deep-link navigation.

Myndral-like means replicating its managed service pattern and modest scale.
Sharing SQL was our cost-saving recommendation, not a user requirement. It avoids
a second SQL baseline near the entire budget. Application databases, SQL login
roles and cloud identities remain separate. Myndral's application credentials and
deployment were not modified. Daily backups at 21:00 UTC and deletion protection
were enabled on the shared SQL instance before provisioning Minkops.

## Capacity, recovery and cost controls

Seven-day SQL CPU maximum was 16.6%; memory components showed 89.75–91.58% free,
with usage peaking at 11.84%. The misleading utilization=100% metric was not used
to size the deployment. Existing data was about 77 MiB; backend series peaked at
seven each. Runtime login `minkops_app` has a 16-connection limit and no DDL,
superuser, role-creation or database-creation rights. `minkops_owner` is NOLOGIN;
`minkops_migrate` is a separate controlled migration identity.

A full pre-provisioning backup completed. A logical restore with PostgreSQL
client 16 compared all 15 migration checksums, 27 tables and the worker wake row.
The subsequent native-context wake migration brings production to 16 checksummed
migrations; its terminal-job trigger is verified in production.
A new full Cloud SQL backup completed after that migration and the production
workflow checks. The original restore proof remains the pre-release baseline.
The temporary restored database and bootstrap SQL login were removed. Match the
dump/restore client to production: client 18 emits settings unsupported by 16.
Restore a logical backup into a new isolated database, compare counts/checksums,
then deliberately cut over; do not overwrite the shared instance as a test.

| Control | Applied setting |
| --- | --- |
| Project budget | CAD 15/month; notifications at 50%, 80%, 100% |
| Cloud Run spend cap | CAD 10/month, this project and Cloud Run only, gross spend excluding credits |
| Scaling | Two HTTP services each max 1, min 0; worker drains one global lane |
| Artifact retention | Delete builds older than 30 days; keep three newest versions per package |
| Hosting retention | Two prior live releases per site |
| Application logs | 30-day retention |

Small pilot estimate: CAD 3–8 incremental/month, with margin below CAD 15. This
is an estimate, not an invoice guarantee. Cloud Run free allowances are shared
across the billing account. An idle hourly job has a one-minute billing minimum:
720 monthly executions without free allowances are about USD 0.82/CAD 1.15 at
an illustrative CAD 1.40/USD. Paid workflow durations, request volume and database
file snapshots add variable costs. Avoid always-on polling, a second SQL instance,
VM/public IPv4, load balancer, Cloud NAT, Redis or Kubernetes at this scale.

Firebase Hosting includes 10 GB storage and 10 GB/month transfer per project;
additional transfer is USD 0.15/GB. The 102.8 MB installer uses roughly 10 GB per
100 full downloads. CDN hits also count. Retained content, artifacts and SQL
snapshots need growth review before opening broad customer traffic.

The Cloud Run cap has enforcement delay and allows in-flight work to finish;
Firebase, SQL, artifacts and other services are outside its coverage. The CAD 15
budget is an alert, not a universal hard cutoff. Check actual spend before larger
rollouts and pause incoming work as projected spend approaches the budget. Do not
disable Myndral's billing account to enforce the Minkops budget.

## Production execution and ownership

The immutable backend image packages core employees and additive client variants.
Current API and worker image is `solution:7556783`, digest
`sha256:9b8ef3bfb755e06be35e66678b1c6dea38c5115c928bdd402749ca6f131db886`.
API revision `minkops-solution-api-00005-s7p` serves 100% of traffic.
Interest image is `interest:6ce25fb`. Every future deployment
must use a distinct reviewed commit tag or digest and record the previous revision.

Worker wake generations commit with workflow changes. Dispatch follows commit,
coalesces under a lease, and can fail without losing durable work. A bounded drain
preserves existing per-run locks/session recovery; a global lane prevents overlap.
Idle acknowledgement is fenced against concurrent enqueue. Completion or failure
of required native Tally references creates a new durable wake even if the run
remains queued; repeated receipts do not create another generation. Hourly recovery handles
lost dispatches. A successful empty execution was verified before live workflows.

The organization disallows allUsers IAM grants. Only the two public HTTP services
disable the Cloud Run IAM invoker check; application session/tenant/CSRF checks
remain active. The worker Job remains IAM-private. `AUTH_DEV_MODE=0` and secure
cookies are explicit. Firebase forwards opaque `__session`; PostgreSQL owns auth.
API responses use private,no-store. SMTP TLS is verified and the fixed EHLO name
avoids a container-host greeting rejected by the relay.

The owner signed up through production email delivery and verified the account.
The isolated `mock-tenant` received only its administrator membership and the two
trusted mock-client workflows. No platform-admin role, fake display tasks or
automatic customer folder grants were seeded. Generated credentials and pairing
state reside only in the operator's private state directory, outside Git.
Installed core Source Discovery is 0.6.1 and mock-client Bill Entry variant is
1.0.2. Client guidance explains the synthetic demo, printed billing reference and
reviewed RC supplier purchase/GST ledger mappings in Test Company;
core instructions, tenant boundaries and financial write checks remain shared.

The following source-discovery and Bill Entry evidence describes the **deployed
pre-refactor contract**, not `accounts/discovery-context`. Source Discovery 0.7.2,
Bill Entry 0.8.1 and companion 0.5.1 require coordinated release and live
acceptance under [MIN-124](https://linear.app/minkops/issue/MIN-124). New runs use
full company context, dated voucher evidence and structure-only Excel projections;
they do not prepare separate Tally references. See [Source Discovery](source-discovery.md).
Production remains at the historical revisions below until that release is approved.

Source catalogs were immutable tenant-owned PostgreSQL JSON snapshots. Bill Entry
pins the reviewed catalog and separately prepares current company references;
schema discovery never exports business records. The real Windows-to-GCP receipt
returned 275 tables, zero records, completed review and accepted identical replay.
Tally repeats some method names at different positions; ordinal column identity
preserves that metadata instead of incorrectly rejecting it.

Hosted Bill Entry run `f3103344-1c14-40c9-a326-9e9e40aca14a` completed using the
reviewed cement invoice. All nine extracted fields matched the fixture. The
native 0.4.1 adapter normalized typed GUID/ALTERID XML values before company and
ledger rechecks. Tally readback found exactly one existing matching voucher;
save reconciliation and replay performed no new import. The server accepted the
same completion receipt twice, and the OpenAI session was deleted successfully.
This proves the existing-voucher path; fresh append evidence remains a separate
test rather than being inferred from duplicate reconciliation. Scanned steel run
`68a19c1f-9f34-49bd-9189-640c215cd794` also completed after normal clarification:
all nine fields matched, exactly one existing voucher was read back, and both
native replay and repeated server receipt were accepted without another import.

Fresh append run `301c95d5-78d6-4acc-9168-b765efe8a922` completed for synthetic
invoice `RC26-CEM-GCP-1002-01`, dated 2 October. Independent pre-read found zero
matching vouchers; all nine reviewed values matched, the native outcome was
`saved`, independent post-read found exactly one matching voucher, replay performed
zero additional imports and the server accepted the repeated completion receipt.
The completed task is
https://app.minkops.com/mock-tenant/tasks/3ef93004-5f56-4f23-8d60-33c466588809.
The local Educational Mode date rejection is preserved separately, with zero writes.

## Repeatable operator deployment

All scripts use authenticated gcloud tokens in memory; no service-account keys.
Use `uv sync --frozen --all-packages`, Node 24 with `npm ci`, gcloud, Docker and
Cloud SQL Auth Proxy. Database restore additionally requires PostgreSQL 16 tools.

1. `bootstrap_hosting.py`: budgets and Hosting sites. Firebase activation requires
   the owner to review its Terms once; Google Analytics was disabled.
2. `provision_database.py` through a loopback proxy on 5433: initial isolated roles,
   database, migrations and runtime grants. Then `verify_database_restore.py`.
   This is initial provisioning, not a routine application deploy command.
3. `configure_runtime.py`: named Secret Manager versions and scoped IAM. Existing
   OpenAI key reuse was explicitly authorized; never print its payload. Rotate by
   creating a version and deliberately updating both API and worker references.
4. Build/push reviewed images, then `deploy_runtime.py --image ... --interest-image ...`.
   Inspect Ready/traffic and Job success, not only gcloud's exit status.
5. Build corporate with `VITE_INTEREST_API_URL=/api/interest`; build console.
   `deploy_hosting.py corporate --installer PATH` verifies the checked-in SHA/size
   before releasing installer, checksum, notes and site together. Deploy console
   separately. `configure_domains.py` reports Google-required records.
6. `configure_retention.py` reapplies bounded retention. Keep rollback artifacts
   before reducing retention; never purge shared SQL as routine cleanup.

Deployments currently run under the authenticated owner account. Repository CI
validates changes. A future unattended pipeline must use repository/branch-bound
OIDC Workload Identity and an explicit production approval environment; no long-lived
GitHub service-account key was installed as a shortcut.

## Website cutover and rollback

Vercel inventory found no project environment variables or non-repository
functions for Minkops. Its Hobby project served `apps/corporate-website/frontend`.
The unrelated `the-gauss-ledger` project must remain untouched.

GoDaddy authoritative DNS now has A `@` → `199.36.158.100`, CNAME `www` →
`minkops-ai-prod.web.app`, CNAME `app` → `minkops-ai-console.web.app` and TXT `@` →
`hosting-site=minkops-ai-prod`. All existing MX, SPF, DKIM, DMARC and verification
records were preserved. Old website records were A `216.198.79.1` and www CNAME
`cname.vercel-dns.com`. Downtime is acceptable; no prolonged dual hosting is needed.

Google-managed HTTPS, www redirect, deep-link refresh, installer hash and the
interest form's SMTP acceptance were verified on the custom domain. The user
approved permanent deletion of `minkops-ai`; Vercel confirmed its removal and the
team retains only the unrelated `the-gauss-ledger` project. Both obsolete Vercel
configuration files were removed from the repository. A previous Firebase Hosting
release and Cloud Run revision provide rollback; the retired Vercel deployment
can no longer provide DNS rollback.

## MIN-123 and MIN-122 completion gates

**Completed:** backend/database deployment; restore and runtime-role checks;
budget/retention controls; worker execution; signup/email verification; HTTPS auth,
cookie, cache, CSRF/logout checks; trusted demo workspace; real metadata-only Tally
discovery and receipt replay; hosted Bill Entry review, fresh append and duplicate reconciliation;
interest-form SMTP acceptance; Windows 0.4.1 installer build/publication with checksum;
custom-domain cutover and approved Vercel project retirement.
Backend/operator suite: 199 tests plus 49 subtests. Operator approval regressions
also pass under optimized Python; explicit authorization guards remain enabled
under `-O` and CI checks unsafe reviews never submit `/approve`.
Web: 17 tests and lint. Native:
35 Linux tests; Windows passes 34 with one privilege-dependent symlink test skipped.

**Still required before marking MIN-123 Done:** the remaining MIN-122 device and
accessibility evidence. Current-PC protocol checks do not prove a clean-PC install.
The user explicitly selected this PC for current verification and left the
clean-PC and remote-server Tally client gates open.

Use `apps/windows-app/tests/production-smoke.mjs` only with an explicit test company
and private owner state, for real schema or workflow-reference receipt checks.
Its explicit save phase is limited to hash-allowlisted synthetic bills in Test Company,
checks independent readback, and replays both the native save and server receipt.
`infra/verify_production.py` launches only reviewed synthetic fixtures and
records actual hosted results. Never substitute fake execution or seed_demo for
production proof. Publish an unsigned **release candidate**, not a signed final
release claim; the download page discloses its actual distribution status.

MIN-122 still needs fresh Windows 10/11 x64 install/launch, driver present/missing,
server-backed Tally through its client, offline/revoked PC, folder refresh, JSON
download, complete Excel/error screen-reader coverage and signing review. Evidence
from the earlier 0.3.1 local UI sweep remains historical. Store release can wait;
scheduling MIN-121 is separate.

## Demo walkthrough

1. Open https://app.minkops.com and sign in with the verified owner. Credentials
   are in the private operator `demo-owner.json`; do not paste them into issue
   comments, slides or screen recordings. Select the release demo workspace.
2. Install 0.4.1 from the corporate download page, connect this PC, and open only
   Test Company in Tally. Keep real customer companies closed during the demo.
   This PC reports Tally Educational Mode: use synthetic fixtures dated on its
   permitted dates (the verified fixtures use 1 or 2 October). Preserve actual
   customer invoice dates; an unsupported date must remain held, never shifted
   to get past a licence restriction. The rejected 8 October release test created
   zero vouchers and is retained in the review history.
3. After the MIN-124 release, run Source Discovery for all authorised loaded Tally
   companies and the selected inclusive voucher period. Review identities, master
   and voucher counts and any evidenced subjective notes, then confirm/export
   the versioned package. Tally context contains complete native business records;
   Excel discovery contains structure and formula text without business rows.
4. Launch Bill Entry with the reviewed RC invoice and confirmed context package.
   Select locked-company or inferred-company mode. Show hosted extraction,
   buyer/company evidence, arithmetic and review before any native write.
   Client allocation guidance overlays the core workflow; write safeguards remain
   enforced by the shared platform and native adapter.
5. Approve only the reviewed values. Show Tally destination readback and task
   completion. Re-running the same invoice reconciles its existing voucher without
   creating a duplicate. Keep the earlier failed identity check in the audit log.
6. Demonstrate a held/rejected review and disconnected-PC recovery without
   touching customer records. Retain recovery state until the server acknowledges
   completion. Finish with known limits: unsigned RC, device/accessibility matrix,
   simple accounting Purchase mapping and unsupported complex allocations.

The hosted walkthrough has exercised source confirmation/JSON output, normal
owner login, extraction, clarification, browser review controls, duplicate
reconciliation and fresh Tally save/readback. Use the completed task above as
the fresh-save evidence; submitting its invoice again should report a duplicate.
Native installation, disconnected-device and accessibility scenarios still need
their separate MIN-122 evidence. Do not present those planned demo steps as done.

## Official references

- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Hosting quotas](https://firebase.google.com/docs/hosting/usage-quotas-pricing)
- [Hosting routing/cookies](https://firebase.google.com/docs/hosting/cloud-run)
- [SQL memory](https://docs.cloud.google.com/sql/docs/postgres/optimize-high-memory-usage)
- [Billing spend caps](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
- [Artifact cleanup](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
