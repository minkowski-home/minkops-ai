# Statement entry

Statement entry 1.0 reads CSV and XLSX bank statements for one client business and
saves reviewed rows as verified Payment, Receipt and Contra vouchers in that client's
Tally companies. It runs on the run model (`platform/work.py`) and tool sessions
(`runtime/openai_hosted.py`), through the handler in
`platform/src/minkops_platform/accounts/statement_entry.py`. Writes need companion
0.11.0 or later.

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
  sheet (the first 60 and last 15 rows plus candidate summary rows) and answers with
  the reading, constrained to the layout's schema (`READING`). Minkops applies the
  reading to the whole sheet and proves it:
  - every running balance must equal the previous one plus the transaction;
  - declared summary controls (opening, closing, total withdrawals and deposits) must
    match, wherever they sit in the sheet, and so must every copy of one printed twice,
    such as a closing balance in a header summary and again in the footer. A
    spreadsheet total saved with float error (14985856.630000005 for 1,49,85,856.63)
    reads as its paise amount; a real third decimal is refused;
  - the dates must settle their own day-month order.

  A refuted reading goes back to the session, naming the cell and what differs, at
  most twice. A refuted reading is never stored; a sheet held after the last one
  shows the person that refusal.
- **When only a person can decide** (the date order, or rows with no running balance),
  one Attention card asks once, answered with
  `POST /api/tenants/{tenant}/attention/{item}/decision` and its chosen `action`. The
  sheet's item waits on that answer and reads the rows when it is given; the same
  answer sent twice returns one receipt.
- **A saved layout that a new statement contradicts** is retired, and the sheet's
  format is learned again.

The layout also names the cells that identify the account (account number, bank,
IFSC), so the rows can be matched to the right bank ledger.

## Routing

Rows become records, chunked into items of up to 50 rows, one answer each. Each chunk is routed in its
own session with the lookup tools:

| Tool | What it answers |
| --- | --- |
| `find_company` | The client's companies in scope, with their GSTINs |
| `find_ledger` | Ledgers by name, alias, GSTIN or bank account number (a masked number matches by its last digits) |
| `voucher_types` | Active Payment, Receipt and Contra types |
| `party_history` | How the client booked similar transactions before |
| `open_bills` | A bill-by-bill ledger's open bills, less what the run's other rows settle |
| `cost_centres` | Cost centres with their categories |
| `find_transfer` | Rows in the run that could be the other leg of a transfer |
| `pair_return` | For a returned payment's UTR, the original in the run or in Tally |
| `mapping` | Rows of the client's mapping file that mention a label |
| `memory` | How rows with a payee were booked when a person approved them, by the payee's name |
| `rules` | Every active rule people wrote for the client's statement work, with its ID and version |
| `practice` | How a company keeps its books, such as how it books bank payments |

A row names its payee as the narration prints it, and cites the IDs of the rules it
follows; the server checks each citation and keeps the text the row followed. A
verified row a person approved becomes a routing in the client's memory: the counter
ledger and voucher type for its payee. A lookup by a payee's name also finds a
routing learnt under a name that contains it, or that it contains, and an edit made
in Tally to the saved voucher demotes it and teaches the routing it shows now (see
[Bill entry](bill-entry.md#memory-and-practice)). A row the run's books already
record, posting its amount to its bank within three days under its reference or
UTR, is `duplicate` when proposed. After each sync, held or left-as-is rows a person
has since entered in Tally by hand are found the same way, become `duplicate` noted
"Entered in Tally by hand", and teach their payee's routing.

As in [Bill entry](bill-entry.md#reading-a-file), the session meets companies and
masters only as short references its input and lookups gave it (`C1`, `L12`), and a
row cites only those: the server resolves them to GUIDs before any check, and refuses
one the session was not given. A row cites a cost centre alone; its category follows.

The session's final answer gives every row of the chunk either a selection or an
exception, constrained to the rows' schema (`ROWS`), so its shape cannot be wrong.
Each row is then checked against the pinned company with `validated_plan`:

- the bank ledger is under Bank Accounts;
- the voucher type is an active type of the right family;
- the ledgers are distinct;
- cost centres belong to their category;
- split lines add up exactly to the bank amount;
- the date is on or after the books' beginning;
- a counter ledger that keeps bill-by-bill balances settles open bills, as below.

A rejected row goes back to the same session with why, which answers again with
the rows it rejected or did not receive, at most twice. The model may instead hold
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

When a chunk ends, any row it did not answer holds as `statement_interpretation`.
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
- **Standing approval.** With review mode `only_exceptions`, a clean proposal is
  approved when people approved at least two earlier saves booking its payee the same
  way (`memory.STANDING`); every other row waits for review, as do the exceptions.
  **Write ready rows** still writes every clean row a person chooses to write.

## Bill-by-bill parties

A counter ledger that keeps its balances bill by bill takes the bills each row
settles on its line (`accounts/settlement.py`):

- **Open bills** come from the run's pinned books. Each bill starts at its New Ref or
  Advance, or at the ledger's opening bill when the books begin inside the mirror's
  window, and every Agst Ref settles part of it. Cancelled and optional vouchers
  settle nothing. A bill opened before that window is never offered, because what
  settled it is not mirrored. A run's rows claim what they settle, so two rows never
  settle one balance twice; repeats of a transaction in overlapping statements
  claim it once.
- **Evident allocations are proposed.** A row settles the bills its narration or
  reference names, or the only open bills, at most three, whose balances add up to
  its amount. It goes on account when nothing is open. The session may give `bills`
  itself (Agst Ref, Advance or On Account), and the same rule decides whether they
  stand.
- **Anything else holds** as `bill_unresolved`, with one Settle button per
  allocation: the session's, the named bills, exact matches, oldest first, and on
  account. `settle` with `{"choice": n}` approves the row with that allocation. If
  another row of the run settled one of those bills meanwhile, the row stays held
  and offers what is open now.
- **Limits.** A bill-by-bill ledger can only be the counter line, so a row paying two
  such parties is `unsupported_structure`, and a bank row never opens a bill. Bills
  entered in Tally after a run read the books are not offered to it; start a new
  run once they are entered. Two runs that settle the same bill at the same time do
  not see each other's claims.

## Review and writes

Rows are reviewed on the run's task page ([Accounts desk](accounts-desk.md#in-the-console)),
each settlement choice as its own button. The runs API serves:

- a small status DTO;
- pages of record summaries;
- each record's detail;
- the ledgers a reviewer may choose for a row's bank or other side
  (`GET .../records/{id}/ledgers?role=&q=`), the session's candidates first, never
  the row's own bank as its other side;
- idempotent decisions per record version: `approve`, `choose` (Choose and
  approve: the person's bank ledger, other side and voucher type, checked as a
  session's proposal is, then approved and saved; a refusal changes nothing),
  `alike` (approve every row of the run proposed again as a person chose for
  another row of that payee), `nothing` (Do nothing),
  `retry` (Recheck: the row's PC reads the books afresh, then the row is proposed
  again in a new attempt of its chunk against that copy; a row left as is offers it
  too), `retry_save`, and
  `settle` with the chosen allocation;
- `POST .../runs/{run}/approve`, which approves every ready row that needs no review.

Approving a transfer leg, or a row repeated in another statement, approves the one
row that writes it.

An approved row becomes a durable `native_writes` intent before anything is sent
(`accounts/writes.py`):

- **One write at a time.** A pending intent reserves its destination identity, so no
  other run can write the same transaction until it is verified or released. Each
  PC gets one `tally.write` job at a time, in approval order.
- **Readback.** The companion fences each import locally by the voucher's remote ID,
  writes the protocol 6 voucher and reads it back; the server checks that readback,
  bill references included, exactly against the plan.
- **Native holds.** A hold the companion reports (Tally not running, company not
  open, possible existing voucher, uncertain import) holds the row. Retry save sends
  the same plan, which the companion either finds already in Tally or refuses to
  import twice. A ledger, voucher type or cost allocation that changed in Tally after
  the run read the books holds as `destination_changed`: Recheck reads the books
  again and proposes the row afresh.
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
