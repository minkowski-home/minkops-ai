# OLTP database

Run `docker compose -f infra/compose.yml up -d app_db` from the repository root,
then set `DATABASE_URL=postgresql://minkops:minkops-local@127.0.0.1:5433/minkops_app`
and, from the repository root, run `uv run --all-packages python db/migrate.py`.

SQL files in `migrations/` are ordered and applied transactionally. Never edit an
applied migration; add the next numbered file. The runner checks file hashes.
The warehouse is intentionally empty and does not share this database.

For local manual testing, run `uv run --all-packages python db/seed_demo.py`
with the same `DATABASE_URL`. It creates an empty PR Infra
tenant and a mock tenant with sample employees, workflows, and task timelines.
The generated demo password is printed once. Do not run the demo seed against
a deployed database.

The seed also registers the shared Source discovery and Bill entry definitions
as planned workflows owned by Accounts desk. Their initial database defaults
come from `fixtures/mock_workflows.json`; rerunning registration preserves
operator settings. See `docs/workflow-registration.md` for the separate per-run
contracts and the boundary between registration and execution.
