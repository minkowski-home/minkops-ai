# Corporate Website

The public marketing site for Minkops (minkops.com): a Vite + React + TypeScript
frontend, plus a small Python + FastAPI API for health checks.

The site is built on the Minkops design system in `design/` at the repository root
(flat, hairline-ruled, Readex Pro / Libre Franklin / IBM Plex Mono, Ember as signal and
Rust as action). Read `design/readme.md` before changing anything visual or any copy.

## What is inside

```
frontend/
  index.html              Default meta tags, webfont loading, favicon
  public/favicon.svg      The Ember dot (the brand has no logo artwork)
  src/
    styles/tokens.css     Design tokens, vendored from design/tokens/*.css
    styles/base.css       Element defaults and site-wide utilities
    ui/                   Design-system primitives (Button, Card, Badge, OptionRow,
                          AgentTile, FlowNode, InterruptCard, ...) + ui.css
    layout/               Nav, footer, SiteLayout (scroll + hash handling), Section,
                          PageHero, SeoHead
    content/              Copy and facts as typed data: agent roster, funnel questions
                          and estimate maths, blog metadata, site constants
    sections/             Landing page sections (hero, funnel, roster, console
                          preview, access form)
    pages/                One file per route; blog posts live in pages/blog/
api/                      FastAPI service (health check)
```

## Rules that keep the site consistent

- **One roster.** `src/content/agents.ts` is the only place an agent is defined (name,
  role, department, glyph, and the "right now" line on its card). The roster, hero
  counts, funnel, orchestration diagrams and console illustration all read from it,
  so a new hire is a one-entry change.
- **The console is an illustration.** `src/content/consoleWorkflows.ts` holds the four
  demo businesses. Every name and figure in it is invented, and the page says so.
  Agents referenced there must exist in the roster.
- **Legal copy is verbatim.** The clauses in `src/pages/LegalPages.tsx` need legal
  review before they change; only the page intros are marketing copy.
- **Retired URLs redirect.** Unpublished blog posts are listed in
  `RETIRED_POST_SLUGS` in `src/App.tsx` so old links land on `/blogs`, not a 404.

## Known limitations

- **The waitlist form does not submit anywhere yet.** `src/sections/InterestForm.tsx`
  validates input and shows its confirmation state, but `submitInterest` is a no-op:
  there is no form backend. Visitors see "You're on the list" while nothing is
  stored. Wiring a real endpoint means replacing `submitInterest`; the component
  already handles submitting and failure states.
- **Fonts load from Google Fonts.** No licensed font binaries exist in the repo. If
  woff2 files are supplied, self-host them and drop the Google Fonts link from
  `index.html`.
- **Design tokens are a copy.** `src/styles/tokens.css` is vendored from `design/tokens/`.
  If a token changes there, copy it across.

## Getting started locally

1. `cd apps/corporate-website/frontend`
2. `npm install`
3. `npm run dev` to launch the site on `http://localhost:5173`
4. `npm run build` to type-check and create a production bundle in `dist/`
5. `npm run lint` and `npm run format` before committing

## Backend service (Python + FastAPI)

1. `cd apps/corporate-website/api`
2. `uv sync`
3. `uv run main.py` to start the API on `http://127.0.0.1:5000`

The dev server proxies `/api` to that address (override with `VITE_API_TARGET`).
