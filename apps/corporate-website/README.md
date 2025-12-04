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
