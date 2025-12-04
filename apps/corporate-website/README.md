# Corporate Website

This module contains the public-facing marketing site for pluseleven. It is a lightweight, static experience (HTML, CSS, and JavaScript) that tells the pluseleven story, highlights the suite of autonomous AI employees, and provides contact/social hooks for the organization.

## What is inside

- `index.html` — the landing page with hero, feature, and contact sections.
- `styles/` — CSS modules that define the visual system.
- `images/` — photography and illustration assets hosted via CDN.
- `scripts/` — minimal interactive helpers (currently empty but ready for future enhancements).
- `favicon.ico` — browser icon for the site.

## Getting started locally

1. `cd apps/corporate-website`
2. Serve the directory with a static server (for example `npm install --global http-server` then `http-server . -c-1`).
3. Open the URL shown in the terminal (usually `http://127.0.0.1:8080`) and review the marketing narrative.
4. Update the HTML, CSS, or assets as needed for brand refreshes, then re-upload the folder to your CDN, GitHub Pages, or hosting platform.

## Performance and deployment notes

- Compress any new images before committing (WebP or optimized JPEG/PNG).
- Keep the site static so it can be deployed on any CDN/edge location without additional compute.
- When the brand story expands, treat this module as a standalone front-end; it can live alongside other modules without dependency on the AI suite.
