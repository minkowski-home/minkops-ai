# Corporate Website Backend

Python + FastAPI backend for the corporate website.

## Setup

Run these commands from the repository root. The root uv workspace owns the
shared lockfile and `.venv`.

1. Install all workspace projects and dependencies:
   ```bash
   uv sync --all-packages
   ```
2. Run the server:
   ```bash
   uv run --all-packages uvicorn minkops_corporate_website_api.main:app --reload --host 127.0.0.1 --port 5000
   ```

## Discovery form delivery

The public form endpoint is `POST /api/interest`. It validates the submitted fields,
then sends a notification to the fixed recipient `info@minkops.com` through Google
Workspace Gmail SMTP. The visitor's address is used only as `Reply-To`; the visitor
cannot choose the recipient or sender. This service uses the existing Myndral SMTP
configuration pattern without sharing or changing Myndral's service.

Configure these server-side environment variables in the API deployment, using the
existing SMTP Secret Manager resource references for the first four values:

- `SMTP_HOST`: `smtp.gmail.com`.
- `SMTP_PORT`: `587`.
- `SMTP_USER` and `SMTP_PASSWORD`: the existing Workspace SMTP authentication
  configuration, injected by Secret Manager and never placed in frontend config.
- `SMTP_FROM_EMAIL`: `info@minkops.com` (the public sender alias).
- `SMTP_FROM_NAME`: `Minkops`.

The API accepts mail settings only for Gmail SMTP on port 587 and requires the public
From alias. Its RFC `From` header and SMTP envelope sender use `info@minkops.com`; the
visitor's email is Reply-To. An alias does not prove that every mail client or transport
header hides the authenticated mailbox identity. Before calling privacy verified, inspect
the raw delivered message headers (including `From`, `Sender`, `Return-Path` and
authentication headers) and confirm no private identity is exposed. Use a dedicated
public-domain mailbox if the Workspace alias leaks identity; do not change the current
Workspace setup without Kartik's approval.

The API includes a honeypot and a five-request-per-ten-minute per-process limiter.
Identical submissions are suppressed by a bounded, one-day in-process duplicate guard.
Google Workspace SMTP has no provider idempotency key: accepted or ambiguous attempts
are suppressed in that process, but this is not a durable
cross-instance or restart guarantee. A transport failure after SMTP begins is treated as
ambiguous; the visitor is told not to retry automatically and to email the fixed inbox so
a person can check. Do not log request bodies, credentials, or provider response details.

## Production hosting

The frontend is a static Vite site on Vercel. The FastAPI endpoint is a separate Cloud Run
service; this repository does not rewrite `/api/interest` through the Vercel SPA fallback.
Deploy the API from this directory to the approved Google Cloud project with the existing
SMTP Secret Manager references bound to `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and
`SMTP_PASSWORD`. Set the non-secret `SMTP_FROM_EMAIL` and `SMTP_FROM_NAME` service
variables. The canonical production hosts (`minkops.com` and `www.minkops.com`) use the
checked-in, public Cloud Run URL in the frontend; it contains no credentials. Other
deployment hosts can override it with `VITE_INTEREST_API_URL`. Local Vite development
uses its `/api` proxy, and other preview hosts do not default to the live inbox. The API
CORS allowlist includes the Minkops production origins and local development origins.

The API returns `202` only after the Workspace SMTP server accepts the message; that is
not evidence that the message reached or was read in the target inbox.

### Cloud Run deployment

Build and deploy this directory as a new service; do not update the existing Myndral
service or secret payloads. The pinned `requirements.txt` is exported from the root
`uv.lock`. From the repository root, the deployment command is:

```bash
CORPORATE_API_SERVICE_ACCOUNT="$(gcloud run services describe myndral-api \
  --project myndral-prod \
  --region us-central1 \
  --format='value(spec.template.spec.serviceAccountName)')"
test -n "$CORPORATE_API_SERVICE_ACCOUNT"

gcloud run deploy minkops-interest-api \
  --source apps/corporate-website/api \
  --project myndral-prod \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account "$CORPORATE_API_SERVICE_ACCOUNT" \
  --min 0 \
  --max 1 \
  --set-secrets SMTP_HOST=myndral-smtp-host:latest,SMTP_PORT=myndral-smtp-port:latest,SMTP_USER=myndral-smtp-user:latest,SMTP_PASSWORD=myndral-smtp-password:latest \
  --set-env-vars SMTP_FROM_EMAIL=info@minkops.com,SMTP_FROM_NAME=Minkops
```

The one-instance cap keeps the best-effort duplicate guard shared during ordinary
operation, but scale-down, process restarts and overlapping revisions can still forget
prior submissions. If stronger cross-revision duplicate guarantees become necessary,
add a durable idempotency store before increasing the instance count. The runtime service
identity must already have access to the referenced secrets; this command does not read
or modify their values. After deployment, verify a controlled message in the inbox and
inspect its raw headers before marking the delivery issue complete.
