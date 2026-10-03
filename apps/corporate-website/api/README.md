# Corporate Website Backend

Python + FastAPI backend for the corporate website. This app owns HTTP transport
and bootstrap; submission orchestration lives in `platform/`, and the Google
Workspace SMTP adapter lives in `connectors/`.

## Local development

Run these commands from the repository root. The root `uv` workspace owns the
shared lockfile and `.venv`:

```bash
uv sync --all-packages
uv run --all-packages uvicorn minkops_corporate_website_api.main:app --reload --host 127.0.0.1 --port 5000
uv run --all-packages pytest apps/corporate-website/api/tests
```

The local form server proxies `/api` to `http://127.0.0.1:5000`. Tests use a
stub transport.

## Discovery form delivery

The public form endpoint is `POST /api/interest`. It validates submitted fields,
then sends a notification to the fixed recipient `info@minkops.com` through
Google Workspace Gmail SMTP. The visitor's address is used only as `Reply-To`;
the visitor cannot choose the recipient or sender. This service uses the
existing Myndral SMTP configuration pattern without sharing or changing
Myndral's service.

Configure these server-side environment variables in the API deployment, using
the existing SMTP Secret Manager resource references for the first four values:

- `SMTP_HOST`: `smtp-relay.gmail.com` (Google Workspace SMTP relay).
- `SMTP_PORT`: `587`.
- `SMTP_USER` and `SMTP_PASSWORD`: existing Workspace SMTP authentication
  configuration, injected by Secret Manager and never placed in frontend config.
- `SMTP_FROM_EMAIL`: `info@minkops.com` (the public sender alias).
- `SMTP_FROM_NAME`: `Minkops`.

The API accepts mail settings only for the Workspace SMTP relay on port 587 and requires the
public From alias. Its RFC `From` header and SMTP envelope sender use
`info@minkops.com`; the visitor's email is Reply-To. An alias does not prove that
every mail client or transport header hides the authenticated mailbox identity.
Inspect raw delivered headers (including `From`, `Sender`, `Return-Path`, and
authentication headers) before calling privacy verified. Use a dedicated
public-domain mailbox if the Workspace alias leaks identity; do not change the
current Workspace setup without the required owner decision.

The API includes a honeypot, a five-request-per-ten-minute per-process limiter,
and a bounded one-day in-process duplicate guard. Google Workspace SMTP has no
provider idempotency key: accepted or ambiguous attempts are suppressed only in
that process, not durably across restarts, instances, or overlapping revisions.
A transport failure after SMTP begins is treated as ambiguous; the visitor is
told not to retry automatically and to contact the fixed inbox so a person can
check. Do not log request bodies, credentials, or provider response details.

The API returns `202` only after the Workspace SMTP server accepts the message;
that alone does not prove the message reached or was read in the target inbox.

## Production hosting

The frontend is a static Vite site on Vercel. The FastAPI endpoint is a separate
Cloud Run service. The canonical production hosts (`minkops.com` and
`www.minkops.com`) use a checked-in public Cloud Run URL in the frontend; it
contains no credentials. Other deployment hosts can override it with
`VITE_INTEREST_API_URL`. Local Vite development uses its `/api` proxy, and
preview hosts do not default to the live inbox. The API CORS allowlist includes
Minkops production and local development origins.

### Cloud Run deployment

Build from the repository root so the image packages only the API, platform
service, and SMTP connector needed by this app:

```bash
gcloud builds submit \
  --project myndral-prod \
  --region us-central1 \
  --config apps/corporate-website/api/cloudbuild.yaml \
  .
```

Deploy the resulting image to the dedicated `minkops-interest-api` service;
do not update the existing Myndral service or secret payloads. Bind the existing
Secret Manager references to `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and
`SMTP_PASSWORD`; set non-secret `SMTP_FROM_EMAIL=info@minkops.com` and
`SMTP_FROM_NAME=Minkops`. The runtime service identity must already have access
to the referenced secrets. Deployment uses references only and must not read or
modify their values.

Keep the Cloud Run instance cap at one while using the best-effort process-local
duplicate guard. Scale-down, process restarts, and overlapping revisions can
still forget prior submissions. If stronger cross-revision duplicate
prevention becomes necessary, add a durable idempotency store before increasing
the instance count. After deployment, verify a controlled message in the inbox
and inspect its raw headers before marking the delivery issue complete.
