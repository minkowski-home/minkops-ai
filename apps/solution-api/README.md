# Shared solution API

From the repository root, install all workspace projects into the shared
`.venv` with `uv sync --all-packages`. Set `DATABASE_URL` to the OLTP
PostgreSQL URL and run `uv run --all-packages python -m minkops_db.migrate`
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
