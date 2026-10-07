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
as active workflows owned by Accounts desk for the mock tenant only. Their initial database defaults
come from `solutions/mock-client/employees/accounts-desk/binding.json`; rerunning registration preserves
operator settings. See `docs/workflow-registration.md` for the separate per-run
contracts and the boundary between registration and execution.

Migration 0009 promotes existing durable rows to `workflow_runs` and retains an
updatable `account_runs` compatibility view for Accounts/native callers. It also
backfills trusted execution bindings for current workflows without changing
settings or status. See `docs/workflow-authoring.md` for the standalone
installation CLI and rollout/recovery instructions.

The consolidated branch also retains Bill Entry's original `0009_bill_entry`
and `0010_bill_company_reservation` migrations. Do not renumber or edit either
branch's applied migrations. `0008z_prepare_branch_convergence` and
`0011_complete_branch_convergence` bridge architecture-first databases back
through the required table name, then restore the shared table and compatibility
view. All pending files run inside the existing locked transaction; rows and
foreign-key targets retain their IDs. Fresh, Bill-first, and architecture-first
upgrades are regression-tested, including checksums, paid-session state, and
writes through the compatibility view. Run the normal migrator through 0011;
see [upgrade instructions](../docs/branch-convergence.md).
