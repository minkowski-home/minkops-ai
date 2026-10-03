# Corporate Website

The public Minkops website is a Vite + React + TypeScript frontend with a
small FastAPI service for discovery form delivery.

The site follows the shared Minkops design system in `design/` at the
repository root. Read `design/readme.md` before changing its visual language.
Design tokens are vendored in `frontend/src/styles/tokens.css`; copy any token
changes from `design/tokens/` into the frontend.

## Project layout

- `frontend/` contains routes, customer-facing copy, page metadata, styles, and
  the discovery form.
- `api/` contains HTTP validation, abuse controls, and health-check transport.
- `platform/` contains reusable submission and duplicate-control logic.
- `connectors/` contains the Google Workspace SMTP adapter.

Customer-facing claims must match current evidence. Published routes should
continue to resolve; retired routes redirect intentionally. Keep legal clauses
verbatim unless specifically authorized to change legal text.

## Frontend development

```bash
cd apps/corporate-website/frontend
npm install
npm run dev
npm run build
npm run lint
```

## Form API development

From the repository root, see [`api/README.md`](api/README.md) for local API,
test, container-build, and Cloud Run instructions. The production API target is
configured only for the canonical Minkops website host; local development uses
the Vite `/api` proxy, and non-production preview hosts do not send messages to
the live inbox.
