# Python workspace

The repository uses one uv workspace rooted at `pyproject.toml`. The root
`uv.lock` resolves the Python projects together, and `uv sync --all-packages`
installs them into the root `.venv`. The root `.python-version` pins the
workspace interpreter to Python 3.12.

## Projects

- `apps/solution-api` builds the `minkops_api` package.
- `apps/corporate-website/api` builds the `minkops_corporate_website_api` package.
- `db` builds the `minkops_db` migration and local fixture utilities. SQL
  migrations remain in `db/migrations`.

Each project owns its dependencies and build metadata in its `pyproject.toml`.
There is one lockfile and no per-project virtual environment. Add a Python
component to the root workspace members when it becomes a real Python project;
README-only directories such as `platform/` and `connectors/` do not need
placeholder Python packages.

## Local setup and commands

Run commands from the repository root:

```bash
uv sync --all-packages
uv run --all-packages python -m minkops_db.migrate
uv run --all-packages uvicorn minkops_api.main:app --host 127.0.0.1 --port 8000
uv run --all-packages uvicorn minkops_corporate_website_api.main:app --reload --host 127.0.0.1 --port 5000
```

The solution API loads its local environment from `apps/solution-api/.env`.

## Imports and dependencies

Use package imports, for example `from minkops_api.auth import ...`; do not add
repository paths to `sys.path` or rely on `PYTHONPATH`. An app may depend on
reusable lower-level workspace packages through a workspace source declaration.
Shared libraries must not import or depend on applications. Keep database
migration and fixture utilities under `minkops_db`; keep the SQL files in the
migration directory so their location and ordering remain explicit.
