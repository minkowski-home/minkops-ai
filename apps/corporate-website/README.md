# Corporate Website

This module contains the public-facing marketing site for pluseleven. The experience now runs on a Vite + React + TypeScript stack inspired by Minkowski’s corporate frontend, and all static assets live under `frontend/public`.

## What is inside

- `frontend/` — the Vite + React application whose entry point is `frontend/src/main.tsx`.
- `frontend/public/` — static assets such as `favicon.ico` and the hero imagery.
- `README.md` — this onboarding note.

## Getting started locally

1. `cd apps/corporate-website/frontend`
2. `npm install` (or `pnpm install` / `yarn install` if preferred).
3. `npm run dev` to launch the site on `http://localhost:5173`.
4. `npm run build` to create a production bundle deployable to any static host or CDN.

## Performance and deployment notes

- Optimize imagery before committing (WebP or compressed JPEG/PNG under `frontend/public/images`).
- Keep this experience isolated under `apps/` so marketing can evolve independently from the AI suite living in `services/`.

## Backend blueprint

The corporate site ships with a minimal Flask backend that powers the `/api` proxy used by Vite and serves health checks for orchestration tooling.

1. `cd apps/corporate-website/api/backend`
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `python run.py` to start the API on `http://127.0.0.1:5000`

Blueprints live under `api/backend/app/` so you can add new endpoints or integrate marketing automation without touching the React layer.
