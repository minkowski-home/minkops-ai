# Cut-over

The rebuilt accounts desk goes live on its own Cloud SQL instance, `minkops-books`,
with fresh workspaces. The old build is parked: its commit, images and installer are
kept, so it can be deployed again against the shared instance and the data it has
now. Nothing here has run yet. It waits for the owner's go-ahead, and two things
come first: the manual testing list in the [rebuild plan](README.md#progress) passes
on the local build, and the owner agrees a retention and deletion policy for the
mirrored books ([risks](README.md#risks)).

Commands run from the repository root as the authenticated owner (see
[operator deployment](../../infra/README.md#operator-deployment)). `DIR` is a new
private directory for the new instance's credentials, such as
`~/.local/state/minkops-books`. The parked build's own state stays where it is.

## 1. Park the old build

1. Record the images production runs. Each is tagged with its reviewed commit:

   ```bash
   gcloud run services describe minkops-solution-api --project=minkops-ai-prod --region=us-central1 --format='value(spec.template.spec.containers[0].image)'
   ```

   ```bash
   gcloud run services describe minkops-interest-api --project=minkops-ai-prod --region=us-central1 --format='value(spec.template.spec.containers[0].image)'
   ```

2. Tag the runtime image's commit as the parked build, and push the tag:

   ```bash
   git tag archive/YYYY-MM-DD/accounts-desk-before-rebuild <commit>
   ```

   ```bash
   git push origin archive/YYYY-MM-DD/accounts-desk-before-rebuild
   ```

3. Apply the retention policy with `infra/configure_retention.py`. It keeps every
   image tagged `parked-…`, so tag both images:

   ```bash
   gcloud artifacts docker tags add <image> <image without its tag>:parked-YYYY-MM-DD
   ```

4. Download the installer minkops.com serves. Check its size and SHA-256 against
   `apps/corporate-website/frontend/src/content/windows-release.json` at the tag,
   and keep it.
5. Record each Hosting site's live release.

## 2. Provision the rebuild's database

1. Record the instance tier as a cost decision against the
   [envelope](../../infra/README.md#production), then create the instance once:

   ```bash
   PYTHONPATH=. uv run --all-packages python infra/provision_database.py --sql-project minkops-ai-prod --instance minkops-books --state-dir DIR --create-instance --tier <tier>
   ```

2. Start the Cloud SQL Auth Proxy on `127.0.0.1:5433` for
   `minkops-ai-prod:us-central1:minkops-books`. Create the roles, the database, every
   migration and the runtime grants, then prove a restore:

   ```bash
   PYTHONPATH=. uv run --all-packages python infra/provision_database.py --sql-project minkops-ai-prod --instance minkops-books --state-dir DIR
   ```

   ```bash
   uv run --all-packages python infra/verify_database_restore.py --sql-project minkops-ai-prod --instance minkops-books --state-dir DIR
   ```

3. Configure the runtime. This grants Cloud SQL access in `minkops-ai-prod`. It
   creates the `minkops-books-database-url` and `minkops-books-migration-url`
   secrets beside the parked build's own, which it leaves unchanged, and keeps the
   model key's secret:

   ```bash
   uv run --all-packages python infra/configure_runtime.py --state-dir DIR
   ```

## 3. Deploy the rebuilt app

1. Build and push the images at the rebuild's reviewed commit. Then deploy the API,
   the twelve-lane worker and the recovery service on the new instance, and check
   Ready, traffic and Job success:

   ```bash
   uv run --all-packages python infra/deploy_runtime.py --image <image> --interest-image <interest-image>
   ```

2. Build the console and deploy it:

   ```bash
   uv run --all-packages python infra/deploy_hosting.py console
   ```

3. Package companion 0.11.0 signed and record it in `windows-release.json` (see
   [Windows app](../windows-app.md#build-and-run)). Build the corporate site, then
   publish both:

   ```bash
   uv run --all-packages python infra/deploy_hosting.py corporate --installer <installer>
   ```

   Installed companions update themselves. The rebuilt server needs 0.10.0 on every
   PC and 0.11.0 on a shared server. It neither reads nor writes a PC's Tally until
   that PC updates, and Check Tally connection asks for the update.

## 4. Fresh workspaces

For PR Infra, and each later client:

1. The client's administrator creates an account at app.minkops.com, leaving
   **New workspace name** blank, and verifies their email.
2. Through the proxy, as the runtime role:

   ```bash
   export DATABASE_URL="$(python3 -c 'import json, sys; print("postgresql://minkops_app:{runtime_password}@127.0.0.1:5433/minkops".format(**json.load(open(sys.argv[1]))))' DIR/database.json)"
   ```

   Create the workspace with the administrator as its admin, and install its
   composition: the client business, the Accounts desk with both workflows, and the
   rule the client agreed. Run it with `--dry-run` first, which rolls back:

   ```bash
   uv run --all-packages python -m minkops_api.install_workflows pr-infra --actor-email <administrator> --create-tenant "PR Infra"
   ```

3. The administrator invites members under Access. Each PC installs Minkops, connects,
   and sets its Tally port under Connected PCs; a shared server follows
   [Hosted Tally](../hosted-tally.md). The administrator authorises each company from
   its "New company found" card for the PR Infra client business. The first sync
   reads the current and previous financial years.

## 5. Where PR Infra's statements resume

Each bank ledger resumes the day after the latest voucher the old build entered on
it, which the mirror shows after the first sync. An overlap is never written twice,
but it costs review. A row whose bank already has a voucher of the same date and
amount holds as Possible existing entry, for a check in Tally. A transfer already
entered covers its other leg.

## 6. Verify

- Connected PCs shows each PC ready, on 0.11.0, with its Tally port, and Check Tally
  connection lists only that PC's companies.
- A bill run and a statement run on PR Infra's own files reach review; one approved
  entry of each is saved and verified in Tally.
- Attention groups items by client, and Memory lists the client's agreed rule.

## 7. Roll back

The parked build runs on the shared instance with its own data, which the rebuild
never touched. Never point the rebuilt app at that database; its migrations refuse a
database that holds the old build's work.

1. Restore the corporate site's recorded release first, so the parked installer and
   its update feed are served again.
2. Check out the tag, run `uv sync --frozen --all-packages`, and redeploy with the
   parked images. The tag's own `deploy_runtime.py` targets the shared instance and
   the parked build's secrets, and it redeploys the worker Job, which has no revision
   to route back to:

   ```bash
   uv run --all-packages python infra/deploy_runtime.py --image <parked image> --interest-image <parked interest image>
   ```

3. Restore the console's recorded release while Hosting still retains it (two per
   site). After that, build the console from the tag and deploy it.
4. Reinstall the kept installer on each PC. The rebuilt companion cannot run the
   parked build's jobs, and an installed companion never downgrades itself.

Entries the rebuilt app saved stay in Tally; check them there before the parked
build enters the same period. Keep the parked build's secrets and its access to the
shared instance until the owner retires it.
