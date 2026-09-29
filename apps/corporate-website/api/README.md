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
