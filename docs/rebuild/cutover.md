# Cut-over

The rebuilt accounts desk goes live on its own Cloud SQL instance, `minkops-books`,
with fresh workspaces, and the old build is retired for good. The owner decided on
23 October 2026 not to park the old build: one final logical backup of its database
is kept off-site, owner-only, and its database, roles, secrets, images and installer
are removed. Myndral's shared instance, and everything else Myndral uses (its
databases, users, SMTP secrets and their access), stay untouched.

Sections 1 to 4 ran on 23 October 2026 ([evidence](evidence.md#cut-over-23-october-2026)).
Sections 5 to 7 create each client's workspace, PR Infra's first, and section 8
holds for every later release.

Commands run from the repository root as the authenticated owner (see
[operator deployment](../../infra/README.md#operator-deployment)). `DIR` is a new
private directory for the new instance's credentials, such as
`~/.local/state/minkops-books`. `ARCHIVE` is the owner-only folder outside git for
the old build's final backup, `~/minkops-private/retired-build`.

## 1. Record what production runs

For the record only, nothing is kept for a rollback: the images each service runs,
its latest revision, and each Hosting site's live release.

```bash
gcloud run services list --project=minkops-ai-prod --region=us-central1 --format='table(metadata.name,status.latestReadyRevisionName,spec.template.spec.containers[0].image)'
```

## 2. Provision the rebuild's database

1. Read the tier of Myndral's instance, the owner's chosen tier (about US$15 a
   month; `db-f1-micro` on 23 October 2026), and record it against the
   [envelope](../../infra/README.md#production):

   ```bash
   gcloud sql instances describe myndral-db --project=myndral-prod --format='value(settings.tier)'
   ```

2. Create the instance once with that tier:

   ```bash
   PYTHONPATH=. uv run --all-packages python infra/provision_database.py --sql-project minkops-ai-prod --instance minkops-books --state-dir DIR --create-instance --tier <tier>
   ```

3. Start the Cloud SQL Auth Proxy on `127.0.0.1:5433` for
   `minkops-ai-prod:us-central1:minkops-books`. Create the roles, the database, every
   migration and the runtime grants, then prove a restore:

   ```bash
   PYTHONPATH=. uv run --all-packages python infra/provision_database.py --sql-project minkops-ai-prod --instance minkops-books --state-dir DIR
   ```

   ```bash
   uv run --all-packages python infra/verify_database_restore.py --sql-project minkops-ai-prod --instance minkops-books --state-dir DIR
   ```

4. Configure the runtime. This grants Cloud SQL access in `minkops-ai-prod`, creates
   the `minkops-books-database-url` and `minkops-books-migration-url` secrets, and
   keeps the model key's secret:

   ```bash
   uv run --all-packages python infra/configure_runtime.py --state-dir DIR
   ```

## 3. Deploy the rebuilt app

1. Build and push the images at the reviewed commit on `main`. Deploy the API, the
   twelve-lane worker and the recovery service on the new instance, and check Ready,
   traffic and Job success. Every service sets its Cloud SQL instances, so none keeps
   Myndral's instance attached:

   ```bash
   uv run --all-packages python infra/deploy_runtime.py --image <image> --interest-image <interest-image>
   ```

2. Build the console and deploy it:

   ```bash
   uv run --all-packages python infra/deploy_hosting.py console
   ```

3. Package companion 0.11.5 as an unsigned release candidate on Windows
   (`scripts/windows_build.ps1 -Kind candidate`; see
   [Windows app](../windows-app.md#build-and-run)) and record it in
   `windows-release.json` with `"unsigned": true`. Build the corporate site, then
   publish both:

   ```bash
   uv run --all-packages python infra/deploy_hosting.py corporate --installer <installer>
   ```

   Installed companions update themselves. The rebuilt server needs 0.11.0 on every
   PC and 0.11.5 to create ledgers; it neither reads nor writes a PC's Tally until
   that PC updates, and Check Tally connection asks for the update.

## 4. Retire the old build

Only after the new deployment serves, so the old database no longer changes:

1. Keep one final logical backup. Start a Cloud SQL Auth Proxy on `127.0.0.1:5435`
   for `myndral-prod:us-central1:myndral-db`, and dump the `minkops` database with
   PostgreSQL 16's `pg_dump` as the old migration role, whose connection the
   `minkops-migration-url` secret holds (read it into the environment, never print
   it). Write the dump to `ARCHIVE` (mode 700), and check it lists with `pg_restore -l`
   before going on.
2. Remove the old database and its roles from Myndral's instance, and nothing else:

   ```bash
   gcloud sql databases delete minkops --instance=myndral-db --project=myndral-prod
   ```

   Then drop the `minkops_app`, `minkops_migrate` and `minkops_owner` roles there,
   checking first that they own nothing else.
3. Delete the old build's database secrets, `minkops-database-url` and
   `minkops-migration-url`, in `minkops-ai-prod`.
4. Remove the Minkops service accounts' `roles/cloudsql.client` in `myndral-prod`.
   Keep their per-secret access to Myndral's SMTP secrets, which the new build
   still sends mail with.
5. Delete the Cloud Run revisions that ran the old build, and its images.

## 5. Fresh workspaces

For PR Infra, and each later client:

1. Through the proxy, as the runtime role, with the console's address for the
   sign-up link. If a local PostgreSQL already holds 5433, as the dev stack's does,
   run the proxy on a free port and put that port in the URL:

   ```bash
   export DATABASE_URL="$(python3 -c 'import json, sys; print("postgresql://minkops_app:{runtime_password}@127.0.0.1:5433/minkops".format(**json.load(open(sys.argv[1]))))' DIR/database.json)" PUBLIC_APP_URL=https://app.minkops.com
   ```

   Create the workspace, install its composition (the client business, the
   Accounts desk with both workflows, and the rule the client agreed) and invite
   the client's administrator as its first admin. They need no account yet. Run it
   with `--dry-run` first, which rolls back:

   ```bash
   uv run --all-packages python -m minkops_api.install_workflows pr-infra --actor-email <administrator> --create-tenant "PR Infra"
   ```

2. The command prints the administrator's sign-up link once; it works once, for
   seven days. Send it to them. Running the command again before they join replaces
   the link; once they have joined, it changes nothing.
3. The administrator opens the link, chooses a name and password, and invites the
   others under Access, as admins or members, assigning each member the workflows
   they run ([Workspace access](../workspace-access.md)). Each PC installs Minkops,
   connects, and sets its Tally port under Connected PCs; a shared server follows
   [Hosted Tally](../hosted-tally.md). The administrator authorises each company from
   its "New company found" card for the PR Infra client business. The first sync
   reads the current and previous financial years.
4. Both workflows start on Review everything (`all_outputs`). Keep them there until
   a month of the client's own bills and statements has been run and scored against
   its books: the checks so far ran on a synthetic pack and books built for it
   ([evidence](evidence.md#demo-readiness-regression-checked-live-23-october-2026)).
   Standing approval (`only_exceptions`) waits for that measurement.

## 6. Where PR Infra's statements resume

Each bank ledger resumes the day after the latest voucher the old build entered on
it, which the mirror shows after the first sync. An overlap is never written twice,
but it costs review. A row whose bank already has a voucher of the same date and
amount holds as Possible existing entry, for a check in Tally. A transfer already
entered covers its other leg.

## 7. Verify

- Connected PCs shows each PC ready, on 0.11.5, with its Tally port, and Check Tally
  connection lists only that PC's companies.
- A bill run and a statement run on PR Infra's own files reach review; one approved
  entry of each is saved and verified in Tally.
- Attention groups items by client, and Memory lists the client's agreed rule.

## 8. Roll back

There is no older build to return to. A bad release of the rebuild is rolled back
to its own previous Cloud Run revision and Hosting release; never reverse a database
migration to recover an application revision. Entries the rebuilt app saved stay in
Tally.
