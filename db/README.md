# OLTP migrations

Fresh installations execute **one reconciled baseline**, `migrations/0001_baseline.sql`.
It creates final tables, constraints, indexes, triggers, the updatable compatibility
view and the worker coordination singleton. It does not install demo/client data.

Existing databases retain all rows and migration history. `migrate.py` checks every
recorded checksum against the immutable `archive/pre-baseline` or active migrations,
applies missing legacy SQL to converge either previously released branch, and then
records adoption of the baseline. It never runs baseline CREATE statements over an
existing schema. Unknown history or changed checksums fail the entire transaction.
An advisory lock serializes migration runners. No production database reset is needed.

The baseline's one formatting-only cleanup moved dump-style ALTER statements into
dependency-ordered CREATE definitions. The runner accepts the exact original/new
checksum pair, preserving existing history; any other baseline edit still fails.

The archive is a **compatibility artifact**, not an active fresh-install migration
chain. Never edit or remove it while a supported installation can need it. New
changes go in new ordered files under `migrations/`; never squash again after this
pre-client baseline. Back up and rehearse adoption on a restored database before
deployment (see [production restores](../infra/README.md#production)).

The archive exists because two branches were released before the shared workflow
architecture. Their original `0009` files and `0010` stay byte-identical (the
runner keys versions by full filename stem, so the shared prefix is harmless).
`0008z` runs before both and temporarily restores the `account_runs` table name
their ALTER statements expect; `0011` restores `workflow_runs` and the updatable
`account_runs` view. Each predecessor's source is preserved under the tags
`archive/2026-10-07/*-before-convergence`; recover from one in a new branch.

Tests compare fresh and upgraded schemas and verify preserved paid sessions,
approvals, native write plans, company reservations, checksums and view updates.

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
