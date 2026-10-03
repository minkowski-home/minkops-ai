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
then sends a notification to the fixed recipient `info@minkops.com` through the Resend
Email API. The visitor's address is used only as `Reply-To`; the visitor cannot choose
the recipient or sender.

Configure these server-side environment variables in the API deployment:

- `RESEND_API_KEY`: a restricted Resend API key stored in the host's secret manager.
- `RESEND_FROM_EMAIL`: a sender on a domain verified in Resend, such as
  `Minkops <website@minkops.com>`.

Keep the frontend and API on the same origin where practical. For a separate API host,
set frontend build variable `VITE_INTEREST_API_URL` to the full endpoint URL and allow
only the public site origins in the API CORS configuration. The API returns `202` only
after Resend accepts the message. That response is not evidence that the message reached
or was read in the `info@minkops.com` inbox.

The API includes a honeypot and a five-request-per-ten-minute per-process limiter, plus
provider idempotency for identical form payloads. The in-process limiter is a baseline
for a single service process; a horizontally scaled or serverless deployment needs an
edge/WAF limit as well. Do not log request bodies or provider credentials.
