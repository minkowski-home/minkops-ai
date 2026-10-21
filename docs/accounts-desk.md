# Accounts desk workflows

Bill entry and Statement entry read a client's documents and save reviewed,
verified vouchers in that client's own Tally companies. Both run on one run model;
see [Bill entry](bill-entry.md) and [Statement entry](statement-entry.md). Sessions
use `gpt-6-luna` through the OpenAI hosted Agents API. Its key lives in the
git-ignored `apps/solution-api/.env`, which the API and worker read; it never
reaches the browser, the companion or a session's tools.

## How a run works

1. **Books.** The Windows companion mirrors each authorised company's masters and
   vouchers into the server, read-only and without AI (`accounts/sync.py`, with
   `connectors/desktop/src/sync.js` on the PC). A newly seen company stays pending
   until one card authorises it for a client business. A run asks the client's PCs
   to refresh, then pins one mirror version per company, so every check in the
   run reads the same books.
2. **Items.** A run splits its inputs into items: a bill file, a statement's
   layout, or a chunk of up to 100 statement rows. The worker's lanes claim items
   and run each in its own tool session.
3. **Proposals.** A session looks things up with read-only tools scoped to the
   run, each call logged, and proposes. Its lookups include the client's memory:
   what approved saves taught, the rules people wrote, and how each company keeps
   its books. The server checks every proposal against the pinned books at once,
   and tells the session what it refused and why.
4. **Review.** Each bill or statement row is a record. It moves from `pending`
   through `proposed` or `held`, then `approved` and `writing`, and ends `saved`
   or `duplicate`; Do nothing makes it `deferred`. Decisions are idempotent per
   record version. Under the `only_exceptions` review mode, clean proposals are
   approved once the run is read; the rest wait for a person.
5. **Writes.** An approved record becomes a durable native write
   (`accounts/writes.py`). Each PC runs one `tally.write` at a time; the companion
   saves the voucher and reads it back, and only a readback that matches the
   approved plan saves the record.

Minkops owns authorization, inputs, checks, approvals and writes. The model reads
and proposes; it never writes to Tally. The companion performs every native write,
and never starts, closes or restarts Tally. See
[Windows setup and recovery](windows-app.md).

The review surface arrives in rebuild slice 10. Until then, runs are driven
through the runs API listed in [Bill entry](bill-entry.md#launching-a-run).

## Memory

Each client business keeps a memory per employee (`accounts/memory.py`), shared by
the employee's workflows and looked up only when a session needs it:

- **Learnt entries.** Verified saves a person approved teach how a supplier's bills
  and a payee's bank rows are booked, and the sync's probes, or a person's one-click
  answer, settle how each company keeps its books. Every sync revalidates them: an
  edit made in Tally demotes an entry, and one whose ledgers are gone retires.
- **Rules.** Plain-text instructions only people write, scoped to a workflow or a
  company, versioned, and cited by the proposals that follow them. A solution can
  seed the rules its client agreed at installation, once.

The memory page shows both. Every member who can reach the client reads it, and
only admins change it. See [Bill entry](bill-entry.md#memory-and-practice).

## Recovery

- **Leases.** A lane holds each item under a lease that one heartbeat renews. An
  item whose lane disappears is reclaimed with its saved provider session, and the
  successor reattaches to it; it is the same attempt, never a new paid one.
- **Tool calls.** Every call is logged once per session and call ID, so a repeated
  call gets its logged answer instead of running again.
- **Failures.** A transient provider failure retries with a new session after 30 s
  and then 120 s, at most three attempts. Anything else fails only its own item.
- **Writes.** A pending write reserves its destination identity, so two runs never
  save the same bill or transaction at once. A write interrupted mid-import is never
  sent again; Retry save reconciles with Tally first.
- **Controls.** Pause stops new sessions and writes from starting. Stop is final:
  unsaved records hold, writes no PC has started are withdrawn, and vouchers
  already saved stay.

## Local setup

From the repository root, use an isolated development database. Do not reset a
database whose migration checksum differs; investigate, or create a new one.

```sh
docker compose -f infra/compose.yml up -d app_db
export DATABASE_URL=postgresql://minkops:minkops-local@127.0.0.1:5433/minkops_app
uv sync --all-packages
uv run --all-packages python db/migrate.py
uv run --all-packages python db/seed_demo.py
AUTH_DEV_MODE=1 uv run --all-packages uvicorn minkops_api.main:app --host 127.0.0.1 --port 8000
```

In another terminal with the same `DATABASE_URL`, start the worker:
`uv run --all-packages python -m minkops_api.accounts_worker --lanes 8`. `--lanes`
sets how many sessions run at once (1–16, default 8), and `--drain` exits once idle
for scale-to-zero hosting. Start the Vite app in `apps/solution-web` (`npm run dev`,
port 3000) and sign in at `/login` as `demo@example.com` with the password the seed
prints. The seed installs the mock-client composition, Statement entry and Bill
entry, for the mock tenant, and keeps existing settings and paused workflows.

Reads and saves need the [Windows companion](windows-app.md) connected to a PC with
the companies open in Tally. The [five-company rehearsal](tally-rehearsal.md) seeds
synthetic companies and bills for that.

## Scope and verification

- **Sources** hold at most 100 files, 5 MB each and 30 MB in all.
- **Bill runs** take 1–50 PDF or image files, 40 MB in all.
- **Statement runs** take CSV and XLSX; convert legacy XLS in Excel.

Offline tests replace only the paid session boundary, with scripted sessions that
call the real tools. They cover the database, authorization, tenant isolation,
approvals, stops, receipt replay and write reservations. Set `TEST_DATABASE_URL` to
a PostgreSQL role that can create databases: pytest creates, seeds and drops its
own database (see [isolated integration tests](../db/README.md#isolated-integration-tests)).
