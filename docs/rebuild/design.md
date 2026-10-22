# Rebuild design

How the [rebuild decisions](README.md) become code. This page is the
implementer's map: modules, tables, protocols and the facts measured on the
live TallyPrime that shaped them. Decisions themselves live in the README;
anything here that contradicts it is a bug in this page.

## Measured on TallyPrime (21 October 2026)

Measured against TallyPrime Edit Log 1.1.7.2, Educational mode, with the five
rehearsal companies open:

- `Company` exposes `AltMstId`, `AltVchId`, `LastVoucherDate`, `BooksFrom`,
  `GUID` and `CompanyNumber` in one collection read.
- A `Voucher` collection with `<FILTER>` `$AlterID > N` returns exactly the
  changed vouchers (61 ms for 8 records).
- Per-date counts need a **source collection**: `BY` and `AGGRCOMPUTE` on a
  plain typed collection are ignored and return every voucher. The working form
  is `SOURCECOLLECTION` + `BY VchDate:<numeric date>` + `AGGRCOMPUTE VchCount:Sum:1`.
  Its counts summed exactly to the voucher census (76 = 76).
- Edit Log exposes `ISDELETED` and `ISDELETEDVCHRETAINED` on vouchers. Deleted
  vouchers may therefore be retained; the sweep treats a retained-deleted
  voucher exactly like a missing one and never relies on the flag alone.
- GST registrations are `TAXUNIT` masters; company and bank details sit on
  `COMPANY`/`LEDGER` records (`BANKDETAILS`, `IFSCODE`). The synthetic
  companies carry none, so GSTIN and account-number matching are proved with
  unit tests and the private PR Infra files.
- Educational mode rejects vouchers not dated the 1st, 2nd or 31st. Write
  fixtures use those dates; a date-only rejection of a real-data row is an
  environment limit, not a product failure.

## Module map

Dependencies flow apps → platform → connectors. New modules sit beside the old
ones until a slice deletes what it replaces.

| Layer | Module | Owns |
| --- | --- | --- |
| platform | `clients.py` | Client businesses, per-client access, company authorisation |
| platform | `files.py` | Uploaded sources and their current files: safe paths, content checks |
| platform | `work.py` | Runs, items, records, decisions, leases, wake-ups, small status DTOs |
| platform | `lanes.py` | Worker lanes: claim, lease renewal, handoff, LISTEN wake-ups, session cleanup |
| platform | `runtime/tools.py` | MCP-shaped tool contracts, argument validation, bounded results |
| platform | `runtime/openai_hosted.py` | Tool sessions: create, answer `requires_action`, reattach, cancel |
| platform | `accounts/mirror.py` | Versioned mirror storage, visibility, GC and lookup queries |
| platform | `accounts/sync.py` | Sync plans, page acceptance, regression and census guards, publish |
| platform | `accounts/practice.py` | Deterministic practice probes and one-click practice questions |
| platform | `accounts/memory.py` | Structured entries, plain-text instructions, learning, demotion |
| platform | `accounts/desk_tools.py` | The Accounts lookup tools and their run scope |
| platform | `accounts/holds.py` | The closed hold-code list and the actions each code allows |
| platform | `accounts/bill_entry.py` | Bill items: pages, session input, `propose` checks, plans |
| platform | `accounts/statement_entry.py` | Statement items: layouts, chunks, pairing, `propose` checks, plans |
| platform | `accounts/writes.py` | Native write intents, reservations and receipts for runs |
| connectors | `documents.py` | Bill pages as bounded images, with each PDF page's text layer |
| connectors | `desktop/src/sync.js` | Read-only incremental collection: markers, deltas, counts, census |
| connectors | `desktop/src/voucher.js` | The native writer, protocol 6 (bill-wise and inventory added) |
| platform | `desktop-runtime/src/jobs.js` | Companion job execution shared by Electron and the headless runner |

Reused unchanged where possible: `accounts/vouchers.py` (bill gate, identity,
receipts), `accounts/statement_layouts.py`, `validated_plan` in
`accounts/statement_routing.py`, `accounts/supplier_gst.py`,
`connectors/src/minkops_connectors/statement.py`, `attention.py`,
`run_controls.py`, `desktop.py` and the installation service.

## Tenancy

`tenants.client_scoping` is false for a single business (every member reaches
every client business) and true for an accounting practice (members reach only
the clients granted in `client_access`; admins reach all). Tenant → client
business → company. Tasks carry `client_id`, so the dashboard, Attention and
runs filter by the clients a member can reach.

A company is identified by PC, GUID, BooksFrom, name and company number:

- all five equal: the same company;
- same PC, GUID and BooksFrom but a new name or number: the same company,
  rebuilt in full;
- same GUID with another BooksFrom: a different company (a split sibling),
  raised as a new company.

A newly seen company is `pending` and is never mirrored until one card
authorises it for a client business.

## Mirror

`mirror_versions` has one row per company and version, carrying its markers,
coverage and state (`building`, `published`, `abandoned`). At most one version
builds per company. `mirror_masters` and `mirror_vouchers` rows carry
`synced_in` and `superseded_in`. A row is visible at version *V* when
`synced_in ≤ V` and (`superseded_in` is null or `> V`). Upserting at *V*
supersedes the current row and inserts the new one; a tombstone only
supersedes. Runs pin `{company_id: version}` and read nothing newer, so a sync
can publish while a run is still reading. Indexed search columns (`name_key`,
`gstin`, `bank_account`, `part_number`, `hsn`, `party_key`, `ledgers`) serve the
lookup tools. `mirror_bill_refs` derives New Ref and Agst Ref rows for
`open_bills`.

Rows superseded before the oldest version any unfinished run pins are garbage
collected.

## Sync protocol

A sync is one `tally.sync` desktop job; the server decides and the companion
collects.

1. The companion reads open companies with their markers *first* and uploads a
   `companies` page.
2. The server records identities, raises cards for new companies, applies the
   regression guard, and answers per company: `skip`, `delta` (with the stored
   AlterIDs) or `full`, plus whether to `sweep`.
3. The companion uploads bounded pages: masters per type, vouchers in date
   batches of at most 5,000 (sized by per-date counts), census pages, and
   refetches by GUID. Each page is idempotent by `(job, seq)` and digest, and is
   applied to the building version in its own transaction.
4. The sweep compares per-date census with per-date counts. Only dates whose
   census count equals the independent count may tombstone a missing GUID;
   changed AlterIDs and voucher numbers are refetched.
5. The finish receipt publishes each complete version with the markers read in
   step 1, then runs the practice probes and revalidates memory. An incomplete
   version is abandoned and reverted.

Requests to Tally are sequential with long timeouts. Nothing in a sync uses AI
or authorises a write.

## Runs, items and records

- `runs` holds one row per launch: client, workflow, pinned definition and
  bundle digest, mirror pins, small config. There are no snapshots and no
  scheduling state in JSON.
- `run_items` is the scheduling unit: one bill, one statement chunk, or one
  layout. Each row carries its state, lease, attempt and provider session IDs.
  Its states are `waiting`, `queued`, `running`, `done`, `failed` and
  `cancelled`; what a bill or row needs is its record's status.
- `run_records` is the review unit: one bill or one statement row, with facts,
  proposal, checks, hold code, review flags, plan and native observation. A
  record waits as `pending` until its session proposes it, then moves through
  `proposed` or `held`, `approved`, `writing`, and `saved` or `duplicate`;
  Do nothing makes it `deferred`. Its `version` increments on every change.
- `record_decisions` is unique per record version. Replaying the same actor's
  same action returns the stored receipt; anything else conflicts and returns
  the receipt that won.
- `native_writes` holds durable intents. Pending rows are unique by
  `(destination_key, identity)`, which reserves each company bill.
- `tool_calls` logs every lookup and proposal per session and call ID, with
  bounded results.
- `item_refs` holds the references an item's lookups issued, each naming one
  company or master for the whole item.
- `item_sessions` records every provider session an item opened, one per
  attempt, with the usage its turn reported. A run's spend is their sum
  (`work.usage`): a retry or a recheck adds a session rather than replacing one.

A trigger bumps `worker_wakeup` and `pg_notify('minkops_work')` whenever an item
becomes `queued`. Releasing a dependency is therefore a committed state change,
never a config edit. The task processing clock counts running items alongside
native jobs.

Run status is a small DTO: counts by state, blockers with Attention links, a
bounded page of record summaries, and an activity version. Record detail is a
separate read.

## Tool sessions

Sessions use `environment: {"type": "none"}`. That removes hosted environment
preparation, and with it files and result artifacts. Bill pages arrive as
`input_image` content. Tools are function tools declared from MCP-shaped
contracts (name, description, input schema) that accept lists of subjects.

Companies and masters reach a session as short references (`C1`, `L12`) its
input and lookups issue, never as GUIDs (`desk_tools.Desk.issue`, `item_refs`).
A proposal cites only references its item was given; the server resolves them
to GUIDs at the tool boundary, so checks, plans and stored proposals read GUIDs
as before. A guessed GUID could name another real master, since Tally numbers a
company's masters in sequence; an unissued reference names none, and is refused.

The worker answers `agent.session.requires_action` with
`agent.session.input.tool_result`, using an idempotency key derived from the
call ID. It answers only the calls a fresh `retrieve` lists as pending: a
re-attached stream replays old `requires_action` events, and the provider
accepts a repeated answer silently. After a restart it answers the pending
calls, then reattaches to the event stream, which replays from the start;
events are deduplicated by ID.

A conversation-only session must be created together with its input, and
creation is not idempotent. Before creating one the item records
`session_requested_at`, and the session carries the item and attempt in its
metadata. A creation whose response was lost is found again by that metadata
in the newest-first session list; a second session is started only when none
is found.

Turn usage is recorded seconds after the turn ends. The lane finishes the item
at once; a closer pass records the usage from the turn, then deletes the
session. A session a retry abandons is closed the same way, so its usage counts
too. The closer works from `item_sessions`, so a restarted worker closes what
its predecessor left.

`propose` is checked immediately. The agent gets at most two resubmissions,
and a resubmission that changes printed facts is flagged for review. A hold
from a final check (a date outside the books, a missing supplier) stays for the
rest of the reading. The session learns only whether a proposal was accepted,
never its review notes, so it cannot rebook a sound proposal to avoid review.
The accepted proposal is the item's result. An invalid call is answered with
its most specific schema error.

Lanes are threads sharing a small connection pool. A lane holds a connection
only while it answers a call or records state, never while it waits on the
model.

- **Fences.** Every write a lane makes (provider IDs, tool answers, the
  finish) is fenced by the item's lease token. A lane whose item was
  reclaimed stops without writing or cancelling.
- **Heartbeat.** One heartbeat renews every lease the host holds. It flags a
  lost fence, and a stopped task, which cancels the turn. A paused task lets an
  underway session finish.
- **Wake-ups.** LISTEN on `minkops_work` wakes idle lanes the moment a commit
  queues an item; a slow poll covers a lost notification.
- **Handoff.** On exit the host expires its leases instead of releasing its
  items, so the next worker reattaches to the same paid sessions.
- **Retries.** Transient turn failures (rate limit, overload, server error,
  timeout) retry with a new session after 30 s and then 120 s, at most three
  attempts. Anything else fails only its item, with the provider's reason.
- **Hosting.** The lanes run inside the existing worker process. Its drain
  acknowledges the wake-up generation only when no item is runnable, and the
  recovery sweep treats a runnable item as work.

## Writer protocol 6

Plans are v5 plus two additions:

- `lines[].bills`: New Ref and Agst Ref allocations, each with a name, type and
  amount;
- `inventory`: entries with item, quantity, rate, unit, amount, godown
  allocations and the purchase ledger.

Readback compares every allocation and inventory line. The server serves v6 only
to companions advertising plan version 6 (companion 0.10.0, the new minimum).
Companion 0.10.0 still executes v5 plans.

## Dev channel

`npm run package:win:dev` builds **Minkops Dev** with its own app ID, install
folder and profile and no update feed, pointed at `http://127.0.0.1:3018`. It
can be installed beside the production companion without touching it.
