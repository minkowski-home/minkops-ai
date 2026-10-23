# OLTP migrations

Fresh installations execute **one reconciled baseline**, `migrations/0001_baseline.sql`,
then every later file in `migrations/` in order. `migrate.py` records each with its
checksum. Unknown or changed history fails the entire transaction, and an advisory
lock serializes runners. New changes go in new ordered files; never edit one that
has been applied, and never squash again.

The baseline's one formatting-only cleanup moved dump-style ALTER statements into
dependency-ordered CREATE definitions. The runner accepts the exact original/new
checksum pair; any other baseline edit still fails.

The rebuilt accounts desk starts on a fresh database (see
[cut-over](../docs/rebuild/cutover.md)); the parked build keeps its own. A database
whose history predates the baseline holds that build's work and is refused, and
migration `0032`, which drops the old runtime's tables, refuses a database that
still holds its rows. The archived pre-baseline history and its convergence path
left with the old build. Its source stays in git history, under the tags
`archive/2026-10-07/*-before-convergence`, and in the parked build's own tag.

## Isolated integration tests

Set `TEST_DATABASE_URL` to a PostgreSQL server URL whose role can create databases,
then run pytest from the repository root. `conftest.py` uses `db.testing` to create
a uniquely named database, apply migrations and seed synthetic fixtures before
test modules load. It drops only that database during cleanup and restores the
original environment. The database named in the supplied URL is not the test
target. CI uses PostgreSQL 16.

```sh
TEST_DATABASE_URL=postgresql:///postgres AUTH_DEV_MODE=1 uv run --all-packages pytest platform/tests apps/solution-api/tests connectors/tests db/tests apps/corporate-website/api/tests infra/tests scripts/tests -q
```

Without `TEST_DATABASE_URL`, database-backed tests are skipped. Use pytest for
this isolation lifecycle; direct unittest discovery does not load `conftest.py`.
