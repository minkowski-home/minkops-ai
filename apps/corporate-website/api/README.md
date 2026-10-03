# Corporate website API

This FastAPI service validates discovery form requests and exposes the health
route used by Cloud Run. Transport and request handling live here; submission
orchestration is in `platform/`, and Google Workspace SMTP is isolated in
`connectors/`.

## Local development

From the repository root:

```bash
uv sync --project apps/corporate-website/api
uv run --project apps/corporate-website/api uvicorn minkops_corporate_website_api.main:app --reload --port 5000
uv run --project apps/corporate-website/api pytest
```

The local form server proxies `/api` to `http://127.0.0.1:5000`. To submit a
real message, configure the SMTP settings listed in the service deployment
runbook; tests use a stub transport.

## Inquiry delivery

The public `POST /api/interest` endpoint sends to the fixed inbox
`info@minkops.com`. Visitor addresses are used only as `Reply-To`; the recipient
and public sender are fixed. Configure `SMTP_HOST=smtp-relay.gmail.com`,
`SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL=info@minkops.com`,
and `SMTP_FROM_NAME=Minkops`. The existing SMTP authentication values are
injected from Secret Manager references and must not be copied into frontend
configuration or image contents.

The connector uses STARTTLS and `minkops.com` as its EHLO identity. Logs contain
only delivery phase, exception class, a numeric SMTP response code, and a
whitelisted reason category; they never include provider text, account
addresses, credentials, or submitted content. Connection/TLS/authentication
and explicit server refusals are confirmed pre-acceptance failures. A timeout
or disconnect during message submission is ambiguous and suppresses automatic
same-process retry.

For a no-email runtime check of relay reachability, TLS, and authentication, run
`python -m minkops_connectors.smtp_diagnostics` in the configured service image.

## Container build and Cloud Run deployment

The Docker build uses the repository root as its context so it can package the
API, platform service, and connector without copying unrelated applications:

```bash
docker build -f apps/corporate-website/api/Dockerfile -t minkops-interest-api .
```

For Cloud Run, submit that same root context with
`gcloud builds submit --project myndral-prod --region us-central1 --config apps/corporate-website/api/cloudbuild.yaml .`,
then deploy the image to the dedicated `minkops-interest-api` service. Keep
existing secret references in Secret Manager; never put SMTP credentials in the
image, frontend bundle, or command-line output.

The duplicate guard and rate limiter are process-local and best-effort. Cloud
Run restarts or additional instances do not share their state, so they are not
durable exactly-once or global abuse controls. If SMTP disconnects after a
send attempt starts, the API reports an uncertain outcome and suppresses an
automatic same-process retry rather than risking a duplicate.
