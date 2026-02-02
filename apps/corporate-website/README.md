# Corporate Website

This module contains the public-facing marketing site for pluseleven. The experience runs on a Vite + React + TypeScript frontend with a Python + FastAPI API for health checks and future marketing endpoints.

## What is inside

- `frontend/` — the Vite + React application whose entry point is `frontend/src/main.tsx`.
- `frontend/public/` — static assets (favicon, hero photography) and a `legacy/` folder containing the previous plain-HTML layout, scripts, and styles.
- `api/backend/` — Python + FastAPI service (health check today, marketing endpoints later).
- `README.md` — this onboarding note.

## Getting started locally

1. `cd apps/corporate-website/frontend`
2. `npm install` (or `pnpm install` / `yarn install` if preferred).
3. `npm run dev` to launch the site on `http://localhost:5173`.
4. `npm run build` to create a production bundle deployable to any static host or CDN.

## Performance and deployment notes

- Optimize imagery before committing (WebP or compressed JPEG/PNG under `frontend/public/images`).
- Keep this experience isolated under `apps/` so marketing can evolve independently from the AI suite living in `services/`.

## Backend service (Python + FastAPI)

The corporate site ships with a minimal Python backend that serves health checks for orchestration tooling.

1. `cd apps/corporate-website/api/backend`
2. `uv sync`
3. `uv run src/main.py` to start the API on `http://127.0.0.1:5000`

The API entry point lives in `api/backend/src/main.py`, so you can add new endpoints or integrate marketing automation without touching the React layer.
