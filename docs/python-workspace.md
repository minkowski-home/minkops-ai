# Python workspace

The repository uses one uv workspace rooted at `pyproject.toml`. The root
`uv.lock` resolves the Python projects together, and `uv sync --all-packages`
installs them into the root `.venv`. The root `.python-version` pins the
workspace interpreter to Python 3.12.

## Projects

- `apps/solution-api` builds the `minkops_api` package.
- `apps/corporate-website/api` builds the `minkops_corporate_website_api` package.
- `platform` builds the `minkops_platform` package.
- `connectors` builds the `minkops_connectors` package.
- `db` is a virtual uv project for migration and local fixture tooling. Its
  scripts and SQL migrations remain together in `db/`.

Each project owns its dependencies in its `pyproject.toml`; installable projects
also define their build metadata. There is one lockfile and no per-project
virtual environment. `platform/` and `connectors/` have package boundaries now
so reusable code can grow under their respective `src/` directories.

## Local setup and commands

Run commands from the repository root:

```bash
uv sync --all-packages
uv run --all-packages python db/migrate.py
uv run --all-packages uvicorn minkops_api.main:app --host 127.0.0.1 --port 8000
uv run --all-packages uvicorn minkops_corporate_website_api.main:app --reload --host 127.0.0.1 --port 5000
```

The solution API loads its local environment from `apps/solution-api/.env`.

## Imports and dependencies

Use package imports, for example `from minkops_api.auth import ...`; do not add
repository paths to `sys.path` or rely on `PYTHONPATH`. An app may depend on
reusable lower-level workspace packages through a workspace source declaration.
Shared libraries must not import or depend on applications. Add a workspace
dependency when an application starts importing `minkops_platform` or
`minkops_connectors`. Run `db/migrate.py` and `db/seed_demo.py` as repository
tools; they are not application imports or distributable packages.
