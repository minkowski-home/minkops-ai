# Statement entry

Statement entry 1.0 reads CSV and XLSX bank statements for one client business and
saves reviewed rows as verified Payment, Receipt and Contra vouchers in that client's
Tally companies. It runs on the run model (`platform/work.py`) and tool sessions
(`runtime/openai_hosted.py`), through the handler in
`platform/src/minkops_platform/accounts/statement_entry.py`. Writes need companion
0.10.0 or later.

## Launch

`POST /api/tenants/{tenant}/clients/{client}/runs` with `workflow: "statement-entry"`, the
statement file IDs and an optional `branch_mapping_file_id`:

- The client's authorised companies are the destination scope. A run needs at least
  one, and every PC holding them must still be connected.
- Each of those PCs is asked to refresh its Tally copy. Rows wait for that refresh
  before they are routed, and the run then pins one mirror version per company.
- A repeated request key returns the same run; the same key with other selections
  conflicts.
- Limits: 30 MB of files, 10,000 rows and 100 columns per sheet. Legacy XLS needs
  conversion in Excel.

## Layouts

Each bank format is read through a layout learned once and proved against the
statement's own balances (`accounts/statement_layouts.py`, reader in
`connectors/src/minkops_connectors/statement.py`):

- **A known format** is matched by its header row, after any preamble, and read with
  no AI session.
- **An unseen format** gets a `layout` item. Its session sees a bounded preview of the
  sheet (the first 60 and last 15 rows plus candidate summary rows) and declares the
  reading with `propose_layout`. Minkops applies the reading to the whole sheet and
  answers at once:
  - every running balance must equal the previous one plus the transaction;
  - declared summary controls (opening, closing, total withdrawals and deposits) must
    match, wherever they sit in the sheet;
  - the dates must settle their own day-month order.

  A refuted reading is explained to the session, which has two more attempts. A
  refuted reading is never stored.
- **When only a person can decide** (the date order, or rows with no running balance),
  one Attention card asks once. The sheet's item waits on that answer and reads the
  rows when it is given.
- **A saved layout that a new statement contradicts** is retired, and the sheet's
  format is learned again.

The layout also names the cells that identify the account (account number, bank,
IFSC), so the rows can be matched to the right bank ledger.

## Routing

Rows become records, chunked into items of up to 100 rows. Each chunk is routed in its
own session with the lookup tools:

| Tool | What it answers |
| --- | --- |
| `find_company` | The client's companies in scope, with their GSTINs |
| `find_ledger` | Ledgers by name, alias, GSTIN or bank account number (a masked number matches by its last digits) |
| `voucher_types` | Active Payment, Receipt and Contra types |
| `party_history` | How the client booked similar transactions before |
| `cost_centres` | Cost centres with their categories |
| `find_transfer` | Rows in the run that could be the other leg of a transfer |
| `pair_return` | For a returned payment's UTR, the original in the run or in Tally |
| `mapping` | Rows of the client's mapping file that mention a label |
| `propose` | One proposal per row, checked as it arrives |

`propose` checks each row against the pinned company with `validated_plan`:

- the bank ledger is under Bank Accounts;
- the voucher type is an active type of the right family;
- the ledgers are distinct;
- cost centres belong to their category;
- split lines add up exactly to the bank amount;
- the date is on or after the books' beginning.

A rejected row is told why and can be resubmitted twice. The model may instead hold
a row with a coded exception:

- `company_unresolved`;
- `ledger_unresolved`;
- `classification_uncertain`;
- `branch_unresolved`;
- `unsupported_structure`.

Facts are immutable: a proposal chooses identities, never amounts, dates or
references, and a row the reader held (unreadable value, broken balance, summary
mismatch, uncached formula) cannot be cleared by a proposal. A routing hint such as a
Branch column is a client label, not a bank branch; its meaning comes from the
client's mapping or the evidence.

When a chunk ends, any row it did not propose holds as `statement_interpretation`.
When the last item settles:

- **Transfers.** Legs that name each other become one Contra, written by the leg
  where money leaves; legs that do not mirror each other hold as
  `statement_transfer_unpaired`. A lone leg first looks in Tally for the transfer
  its other leg may already have entered.
- **Overlapping statements.** A transaction in two of them is written once. If the
  two route it differently, both hold as `statement_conflict`.
- **Gaps.** When a statement opens at a different balance from where the previous
  one for that bank ledger closed, one "Transactions missing" item names both; no
  row is held.
- **Standing approval.** With review mode `only_exceptions`, every clean proposal is
  approved; the exceptions wait for review.

## Review and writes

The runs API serves:

- a small status DTO;
- pages of record summaries;
- each record's detail;
- idempotent decisions per record version: `approve`, `nothing` (Do nothing),
  `retry` (Recheck the row in a new attempt of its chunk) and `retry_save`;
- `POST .../runs/{run}/approve`, which approves every ready row that needs no review.

Approving a transfer leg, or a row repeated in another statement, approves the one
row that writes it.

An approved row becomes a durable `native_writes` intent before anything is sent
(`accounts/writes.py`):

- **One write at a time.** A pending intent reserves its destination identity, so no
  other run can write the same transaction until it is verified or released. Each
  PC gets one `tally.write` job at a time, in approval order.
- **Readback.** The companion fences each import locally by the voucher's remote ID,
  writes the v5 voucher and reads it back; the server checks that readback
  exactly against the plan.
- **Native holds.** A hold the companion reports (Tally not running, company not
  open, possible existing voucher, uncertain import) holds the row. Retry save sends
  the same plan, which the companion either finds already in Tally or refuses to
  import twice.
- **Interrupted saves.** A write whose PC stopped before confirming it holds as
  `save_interrupted` once that PC polls again; it is never re-sent automatically.

Identity combines the bank reference, date, signed amount, running balance and
occurrence number, so overlaps reconcile without dropping two real identical
transactions. The voucher's narration tag is a UUID5 of the tenant, company, bank
ledger and that identity.

Pause stops new writes from being dispatched. Stop is final:

- unstarted items are cancelled;
- unsaved rows hold as `run_stopped`;
- writes no PC has started are withdrawn;
- a write already underway still reports its receipt.
