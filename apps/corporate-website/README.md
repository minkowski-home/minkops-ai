# Corporate Website

The public marketing site for Minkops (minkops.com): a Vite + React + TypeScript
frontend, plus a Python + FastAPI API for health checks and discovery-form delivery.

The site is built on the Minkops design system in `design/` at the repository root
(flat, hairline-ruled, Readex Pro / Libre Franklin / IBM Plex Mono, Ember as signal and
Rust as action). Read `design/readme.md` before changing anything visual or any copy.

## What is inside

```
frontend/
  index.html              Default meta tags, webfont loading, favicon (from design/assets/logos)
  src/
    main.tsx              Imports design/tokens/*.css, then the site's own styles
    styles/base.css       Element defaults and site-wide utilities
    ui/                   Design-system primitives, form controls and icons + ui.css
    layout/               Nav, footer, SiteLayout (scroll + hash handling), Section,
                          PageHero, SeoHead
    content/              Funnel questions and workflow outlines, fictional console
                          scenarios, blog metadata, site constants and release metadata
    sections/             Landing page sections (hero, workflow model, funnel,
                          console preview, access form)
    pages/                One file per route; blog posts live in pages/blog/
api/                      FastAPI service (health and discovery form delivery)
```

## Rules that keep the site consistent

- **Describe workflows truthfully.** `src/content/funnel.ts` provides illustrative
  workflow outlines, not live integrations or time-saved estimates. Product scope
  follows the repository's Product Vision.
- **The console is an illustration.** `src/content/consoleWorkflows.ts` holds the four
  demo businesses. Every name and figure in it is invented, and the page says so.
- **Legal copy is verbatim.** The clauses in `src/pages/LegalPages.tsx` need legal
  review before they change; only the page intros are marketing copy.
- **Retired URLs redirect.** Unpublished blog posts are listed in
  `RETIRED_POST_SLUGS` in `src/App.tsx` so old links land on `/blogs`, not a 404.

## Known limitations

- **Discovery form delivery requires deployment setup.** The form posts to a separately
  deployed FastAPI service. Production builds set `VITE_INTEREST_API_URL=/api/interest`
  and Firebase Hosting rewrites it to Cloud Run; other hosts can override that URL.
  The service uses Google Workspace SMTP from server-only
  environment settings. SMTP acceptance is not proof of receipt in
  `info@minkops.com`; see the API README for deployment and verification limits.
- **Fonts load from Google Fonts.** No licensed font binaries exist in the repo. If
  woff2 files are supplied, self-host them and drop the Google Fonts link from
  `index.html`.
- **Tokens come from `design/`.** `src/main.tsx` imports the design system's token files
  through the `@minkops/design` alias, so a token change there reaches the site directly.
  The site uses the default palette; it does not load the console's selectable themes.

## Getting started locally

1. `cd apps/corporate-website/frontend`
2. `npm ci`
3. `npm run dev` to launch the site on `http://localhost:5173`
4. `npm run build` to type-check and create a production bundle in `dist/`
5. `npm run lint` and `npm run format` before committing

## Backend service (Python + FastAPI)

1. From the repository root, run `uv sync --all-packages` to install the Python workspace into its shared environment.
2. Run `uv run --all-packages uvicorn minkops_corporate_website_api.main:app --reload --host 127.0.0.1 --port 5000` to start the API on `http://127.0.0.1:5000`.

The dev server proxies `/api` to that address (override with `VITE_API_TARGET`).
