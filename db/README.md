# OLTP database

Run `docker compose -f infra/compose.yml up -d app_db` from the repository root,
then set `DATABASE_URL=postgresql://minkops:minkops-local@127.0.0.1:5433/minkops_app`
and run `uv run --project apps/solution-api python db/migrate.py`.

SQL files in `migrations/` are ordered and applied transactionally. Never edit an
applied migration; add the next numbered file. The runner checks file hashes.
The warehouse is intentionally empty and does not share this database.
