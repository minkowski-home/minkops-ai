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
