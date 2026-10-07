# Shared solution API

From the repository root, install all workspace projects into the shared
`.venv` with `uv sync --all-packages`. Set `DATABASE_URL` to the OLTP
PostgreSQL URL and run `uv run --all-packages python db/migrate.py`
before starting the API with
`uv run --all-packages uvicorn minkops_api.main:app --host 127.0.0.1 --port 8000`.

Sign-up, email verification, sign-in, tenant memberships, join requests, and
invitations are served under `/api`. Configure `PUBLIC_APP_URL`, `SMTP_HOST`,
`SMTP_FROM`, and optional `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USER`, and
`SMTP_PASSWORD` for verification and invitation email. Set `COOKIE_SECURE=1`
behind HTTPS. For local development only, `AUTH_DEV_MODE=1` returns links in
the API response instead of sending mail.

Verified email domains are discovery hints. Membership is granted through an
invitation or an approved request. Platform administrators are designated
manually in the database during onboarding; public sign-up cannot grant this
role.

Accounts desk launch, review and local-write receipt routes are under
`/api/tenants/{slug}/accounts`. Run the separate durable worker with
`uv run --all-packages python -m minkops_api.accounts_worker`. Both processes
need the same DATABASE_URL; the worker reuses the configured OpenAI key.
See [workflow setup and recovery](../../docs/accounts-desk.md).

Accounts routes own HTTP validation, authentication, CSRF and response mapping.
Application commands and worker execution live in `minkops_platform.accounts`;
workbook mechanics live in `minkops_connectors.excel`. The former Accounts helper
modules remain compatibility imports, and the worker command above is unchanged.
