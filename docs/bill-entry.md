# Bill entry

Bill entry 1.0 reads purchase bills and saves each one as the client's own
reviewed, verified Tally voucher: a Purchase, Journal or Debit Note. It runs on
the accounts desk's run model (`platform/src/minkops_platform/accounts/bill_entry.py`,
the `desk.bill` handler). The mock-client composition installs it for
`mock-tenant`; PR Infra's binding does not yet include it. Sessions use
`gpt-6-luna` through the OpenAI hosted Agents API. The model only reads and
proposes: Minkops owns every check, approval, duplicate search, write and
readback.

## Launching a run

A run covers one client business. It starts from the workflow's page and is
reviewed on its task page; see [Accounts desk](accounts-desk.md#in-the-console).
Both use the runs API, under `/api/tenants/{slug}/clients/{client}`:

| Call | Purpose |
| --- | --- |
| `POST /api/tenants/{slug}/accounts/sources` | Upload bill files (multipart `files` and their relative `paths`); returns their file IDs |
| `POST /runs` | `{workflow: "bill-entry", file_ids, request_key, config}`; a repeated request key returns the same run |
| `GET /runs/{id}/status` | Small status: run state, item and record counts, blockers |
| `GET /runs/{id}/records` | One summary per bill, paged with `after` |
| `GET /records/{id}` | One bill's proposal, evidence, lines and Tally observation |
| `POST /records/{id}/decisions` | `{action, version, detail}`: one of the bill's offered actions, with the detail it was offered with |
| `POST /runs/{id}/approve` | Write ready bills: approve every proposal that needs no review |

Stop and pause are task controls (`POST /api/tenants/{slug}/tasks/{task}/control`).

A run takes 1–50 PDF, PNG, JPEG or WebP files, at most 40 MB together, each
selected once. Its settings are:

- `review_mode`: `all_outputs` (every proposal waits for approval; the tenant
  default) or `only_exceptions` (bills that pass every check and follow the
  client's precedent are written once the whole run is read);
- `company_mode`: `infer` (each bill routes to the company it is addressed to)
  or `locked`, with `locked_company_guid` one of the client's companies.

Each file becomes one item. It waits until every PC holding the client's
companies has refreshed its Tally copy into the server's mirror, then the run
pins that mirror version: every check in the run reads the same books.

## Reading a file

Each file is read in its own tool session: every page as an image, plus the
PDF's text layer where it has one and what any signed e-invoice QR code on it
registers (see [Signed e-invoices](#signed-e-invoices)). The session looks things up in the pinned
books with read-only tools, each logged per call:

- `find_company`: the client's companies, with every GSTIN each is registered under;
- `find_ledger`: by name, alias, GSTIN or bank account, with each ledger's group and description;
- `voucher_types` and `cost_centres`;
- `party_history`: how the client booked a supplier's or a ledger's earlier vouchers, including their stock items
  and the godowns those went to;
- `find_stock_item` and `godowns`: stock items by name, alias or HSN code, with their units, and the company's stores;
- `check_gstin`: whether a GSTIN read from the bill is valid, and its state;
- `memory`, `rules` and `practice`: what Minkops learnt about a supplier, the client's own rules, and how a
  company keeps its books (see [Memory and practice](#memory-and-practice)).

A session meets companies and masters only as short references, never their
GUIDs: the input names each company (`C1`), and every lookup gives the masters it
finds theirs (`L12` for a ledger, `T2` for a voucher type, `S4`, `G1` and `K3` for
stock items, godowns and cost centres). Each stands for one company or master for
the whole file (`item_refs`), so a resumed session keeps the references it read. A
proposal may cite only references its own session was given. Tally numbers a
company's masters in sequence, so a guessed or mistyped GUID could name another
real ledger; a reference no lookup issued names none, and is refused with the
lookup that finds the right one. A cost centre's category follows from the centre.

It then gives its final answer: `count`, the number of bills the file holds, and
the bills numbered in the order they appear. The provider constrains that answer
to the proposal's schema (`PROPOSAL` in `bill_entry.py`), so its shape cannot be
wrong; every value in it still comes from the bill and the lookups. Companion pages
such as e-way bills, challans and annexures corroborate a bill and are never bills
themselves. Each bill is then checked and either accepted, rejected with a reason
the session can act on, or held. What is rejected goes back to the same session,
which answers again with those bills corrected, at most twice
(`tools.CORRECTIONS`); a bill still rejected then holds for that reason. A reading
that changes a printed fact after a refusal goes to review. Where the PDF has a text layer, the
total and any round-off must be amounts that layer prints. When the file is read
again, bills a person has already decided keep their numbers. A bill that follows
one of the client's rules cites its ID, and the proposal keeps the text it
followed. A receipt-register stamp (DMR, GRN or MRN) is read as printed, with its
number and date.

## The gate

`accounts/vouchers.py` `check` binds a proposal to its company's pinned masters
and proves it:

- every identity is a master of the routed company, resolved from the references
  the proposal cites: the voucher type of the right family, the supplier, and a
  distinct ledger per line;
- the supplier's line is computed from the printed total, and the other lines
  reach it exactly;
- each tax line matches its printed rate and taxable value within a rupee, and
  central and state halves agree. Its ledger is one for its head and rate: as
  Tally marks a GST duty ledger, or else as its name says;
- the bill's supplier GSTIN is the supplier ledger's, when the ledger has one;
- the bill's printed taxable and tax totals bind the lines that claim them, so a
  tax-inclusive amount column cannot drop the input tax;
- a printed round-off of at most a rupee is its own line, never folded into the purchase;
- cost centres belong to their category, on a ledger that enables them. A ledger
  the bill splits across centres is one line carrying each centre's share, and a
  ledger taxed at several GST rates is one line per rate (plan protocol 7, which
  only such a bill needs); lines nothing sets apart are summed. A split the bill
  prints between two or more sites or projects is carried on cost centres at its
  printed amounts or percentages, matched by share, or the bill is refused, then
  held;
- TDS follows its section and rate, on the expense value only;
- the date is the one the bill prints: it must agree with the date the session
  quoted (read day first or month first) and be a plausible bill date, or the
  bill is read again. Only then does it fall within the company's books: a bill
  before they begin, or after a year-split sibling takes over, holds at once;
- input tax is claimed only by a registered buyer the bill names: a company with
  GST on in Tally but no GSTIN holds, and a registered company's bill printing no
  buyer GSTIN is read again, then held. A company with GST off keeps its tax
  ledgers as plain bookkeeping;
- what the bill prints as held back or adjusted is carried: retention or
  contractual withholding as a retention line on the supplier's side, which
  reduces what it is owed as TDS does, and a refundable deposit as its own line,
  never expense. An advance already paid is matched in Tally; the bill is booked
  at its full value with a note, so standing approval leaves it to a person;
- a supplier that keeps bill-by-bill balances gets the bill recorded under its
  invoice number (a New Ref on the supplier's line). Its credit note holds as
  `unsupported_structure`, because it must name the bill it adjusts: enter it in
  Tally.

Some holds no later attempt may change, only a person's recheck: a date
outside the books, a foreign supplier's invoice (whose numbering year is
unknown), or a missing supplier. Foreign-currency bills cannot be saved yet, nor
can items Tally keeps in batches (see [Item-wise purchases](#item-wise-purchases)).
The session proposes such a bill as `unsupported_structure`, naming the
structure. A bill that merely lists goods with HSN codes and quantities is
booked to the ledger the client uses, unless the client books such purchases
item-wise.

## Signed e-invoices

An e-invoice carries a QR code its Invoice Registration Portal (IRP) signed. Bill
reading decodes every QR code on a page (`minkops_connectors/documents.py`, from a
300 DPI render) and keeps those that are signed e-invoices
(`minkops_connectors/einvoice.py`). Each is:

- **verified** when a pinned IRP key verifies its signature, within the IRN
  generation period that key signed;
- **altered** when it names a pinned certificate whose signature fails: the bill
  holds at once for a person to check with the supplier;
- **unverified** when its key is not pinned. It is still the invoice's own
  machine-readable data, but no proof the IRP registered it.

The session is told what each code registers. A code belongs to the bill with its
number, or to a file's only bill when it is the file's only code. That bill's
reading must agree with its number, kind, date, total and seller GSTIN; a reading
that does not is refused, saying what the code registers. Its buyer GSTIN must be
one the routed company is registered under, or the bill holds as
`company_unresolved`. A verified code is kept on the bill's facts with its IRP and
IRN.

The pinned keys are production signing keys only, in
`connectors/src/minkops_connectors/einvoice_signers/`, each listed in
`signers.json` with its IRP, IRN generation period, SHA-1 thumbprint (the code's
`kid`) and the official URL it came from. They cover NIC's IRP 1 (August 2020
onwards) and IRP 2 (April 2023 onwards), and IRIS's IRP 6 until June 2026. To add a
key, download it from the IRP's own key page, check its thumbprint against a real
code it signed, and add its entry. Codes from the IRPs not pinned yet (3, 4 and 5),
or from a newer IRIS key, read as unverified.

## Item-wise purchases

A supplier whose purchases the client books item-wise in Tally gets its bills booked
the same way. For each item line of the bill the session proposes, in `voucher.items`:

- the stock item;
- its quantity in that item's own unit, with the printed rate and amount;
- the purchase ledger that carries its value;
- the godowns it goes to.

The gate (`accounts/vouchers.py`) proves:

- each item is a stock item of the company, counted in a simple unit and not kept in
  batches;
- the quantity keeps to its unit's decimal places, and quantity times rate reaches the
  printed amount within a rupee;
- the purchase ledger has inventory values affected, as Tally requires;
- the godowns take the item's whole quantity and amount between them.

Items carry the bill's taxable value. Tally books each purchase ledger's items as one
ledger line, so the plan does too, and its readback must carry every item, godown,
quantity, rate and amount. Only a Purchase invoice carries items; goods returned on a
credit note are entered in Tally.

An item-wise purchase also depends on the company's practice. Where Receipt Notes or
purchase orders track the goods, the purchase must name the note or order it follows,
so the bill holds for entry in Tally, and no later reading can recast it. While either
practice is open, the bill waits on its question, and the answer, or a later sync that
settles it, releases the bill. Confirmation by use tells the two treatments apart: a
supplier booked item-wise before has no precedent for a bill booked to ledgers, and the
reverse.

## Review

Once every file is read, a bill repeated across files is written once, and files
that print different versions of one bill all hold. A proposal goes to review,
whatever the review mode, when:

- it books the supplier differently from every earlier voucher of theirs (another
  voucher type or expense ledger, or without the stock items they carried). The
  note names what the supplier's last bill was booked to beside this one. One
  approval confirms the booking, which memory then holds as a precedent;
- it books the supplier the way someone changed in Tally since Minkops saved it;
- its reading changed after a refusal;
- it is a copy of a bill in another file;
- it was proposed again booked as a person chose for another bill of the same
  supplier in the run (below);
- the same bill (buyer, supplier, number, date and total as printed) is held in
  another file. Each copy names the other, so the proposed one is not written while
  its copy waits for a reason no one has seen. Two held copies name each other
  too, so the one settled first is never entered again from the other;
- it adjusts an advance already paid, which a person matches in Tally.

The session never learns of these notes, so it cannot rebook a sound bill to
avoid review.

Each held bill offers the actions its codes allow. The matrix is defined once in
`accounts/holds.py`, pinned by `platform/tests/test_holds.py`; a code outside it
offers only Do nothing and Recheck.

| Codes | Actions |
| --- | --- |
| `company_unresolved`, `not_a_bill`, `multiple_bills_unclear`, `required_value_missing`, `source_values_conflict`, `source_unreadable`, `unsupported_structure`, `date_before_books`, `date_outside_company_period`, `identity_rule_unknown`, `voucher_type_unresolved`, `extraction_failed` | Do nothing, Recheck |
| `classification_uncertain`, `supplier_unresolved` | Choose and approve, Do nothing, Recheck |
| `supplier_missing` | Create this ledger, Choose and approve, Do nothing, Recheck |
| `company_not_open`, `no_company`, `duplicate_company`, `not_running`, `port_closed`, `busy`, `too_many`, `invalid_response`, `rejected`, `save_waiting`, `save_interrupted`, `save_held` | Retry save, Do nothing |
| `destination_changed` | Do nothing, Recheck |
| `run_stopped` | Do nothing |
| `practice_question` | Do nothing; the answer in Attention releases it |

Every proposal also offers Choose and approve, and a held bill offers it when its
reading is complete, addressed to its company and agrees with what the file
prints, so only its treatment is in question. The person chooses the voucher type,
the supplier and each line's ledger (and an item-wise bill's purchase ledgers)
from a picker that lists the ledgers the session weighed (`candidates`) first,
then the company's ledgers of that role in the run's books
(`GET .../records/{id}/ledgers?role=&q=`). The amounts stay as the bill prints
them. The server rebuilds the proposal with those GUIDs and runs every gate a
session's proposal meets; a choice a gate refuses answers why and changes
nothing, and one it accepts is approved and saved. Once that save is verified,
the run's other bills of the same supplier, held for the same question or
proposed unlike how the books booked the supplier, are proposed again booked the
same way, noted "Booked as you chose for …"; one click, Approve all booked this
way, approves them, and the note keeps standing approval from writing them
unseen. Create this ledger is offered only when the supplier can be created
safely (below). Recheck reads the books afresh first: it asks the PC holding the bill's
company (every company in the run's scope, for a bill with none) to refresh, and
the file's next session waits for that refresh, which must start after the
recheck, then pins the copy it published (`runs.repin`, `desk_tools.ready`). A
ledger created in Tally after the run started is then found. Until then the bill
names the PC it waits for, so an offline PC keeps it waiting visibly. The run's
other bills keep their proposals and the books they were checked against; every
save is verified against Tally as it is. A bill left as is (Do nothing) offers
Recheck, so "do nothing, fix it in Tally, recheck" works, and so does a save Tally
refused because a ledger, voucher type or cost allocation changed after the run
read the books (`destination_changed`). Decisions are idempotent per record
version: the same decision sent twice returns one receipt. Stop is final: unsaved
bills hold as `run_stopped`, writes no PC has started are withdrawn, and a
stopped run offers only Do nothing.

## Memory and practice

Treatment follows, in order: a legible handwritten instruction on the bill, the
client's rules, what Minkops learnt, then the books' history. Tally's masters and
the gate bind all of them. Memory belongs to the client business and the Accounts
desk employee (`accounts/memory.py`):

- **Bookings.** A verified save a person approved is one way its supplier's bills
  are booked: the voucher type and expense ledgers, by GUID, and whether it was
  booked item-wise. Approving the same booking again uses its entry; a supplier
  booked two ways has two. A treatment a person chose in review is learnt the same
  way, its evidence of kind `choice` naming them.
- **Upkeep.** Every sync revalidates the entries. An edit made in Tally to a voucher
  an entry was learnt from, or its deletion, demotes the entry, and the next bill
  booked that way goes to review. An entry whose ledgers are missing from three
  syncs in a row retires. A renamed ledger is still the same booking.
- **Learning from Tally.** A person who corrects a saved voucher in Tally has shown
  its treatment: the edit that demotes the old entry also teaches, once per
  alteration, how the voucher is booked now (evidence `tally_edit`); an amount-only
  edit changes nothing, and a deleted or cancelled voucher only demotes. A voucher
  moved to another supplier teaches recognition instead (below). After each sync,
  the client's bills held for a question, or left as is, that a person has since
  entered in Tally by hand are found there by their document identity, as the
  write-time check finds them (the supplier by the printed GSTIN when none was
  matched): each becomes `duplicate`, noted "Entered in Tally by hand", and teaches
  its booking (evidence `tally_entry`). A bill already in the run's books when it
  is proposed is `duplicate` at once if entered as proposed, or held as
  `already_in_tally` (final) naming what differs; the write-time check still guards
  every save.
- **Supplier recognition.** A printed supplier name a person matched to a ledger,
  by choosing it in review or moving a saved voucher to it in Tally, is kept as a
  `supplier_name` entry, only when the session quoted that name and no printed
  GSTIN conflicts with the ledger's. `find_ledger` lists that ledger first, marked
  learnt; a later different choice demotes it. Recognition finds a supplier; it
  never decides how a bill is booked.
- **Rules.** Plain-text instructions only people write, scoped to a workflow or
  company, versioned and cited by ID. Sessions read every active rule in scope,
  so a client keeps at most 30 active rules per employee.
- **Practice.** After every sync, deterministic probes settle how a company keeps
  its books, such as where it types invoice numbers, whether it records
  receipt-register numbers, whether Receipt Notes or purchase orders track its
  goods, whether purchases post GST to the ledgers Tally sets up as GST duties or to
  others named for the tax, and whether a printed discount is booked net or to a
  discount ledger. A probe the history cannot settle raises one one-click question per
  company in [Attention](attention.md). Each mirror version records the probes run
  on it, so a probe added later meets books that have not changed since.

Practice shapes the plan. A company that records receipt-register numbers in the
narration gets the stamp there. Once settled, the gate enforces the GST ledgers and
discounts a company uses: a GST line on a ledger merely named for the tax is refused
where the company posts to a duty ledger for that head and rate, naming it, and a
discount line where the company books net. A taxed bill, or one with a discount line,
waits while that question is open. While that question is open, a bill with a stamp
holds as `practice_question`; the answer re-checks it, and standing approval then
writes a clean one. Duplicates are sought where the company types invoice
numbers, or in both the reference and the narration while that is unsettled.

The memory page shows a client's entries, with their status and the evidence
behind them, and its rules. Every member who can reach the client reads it, and
only admins disable, enable or delete entries or change rules
(`/api/tenants/{slug}/clients/{client}/memory`).

## GST returns

Tally's GST returns read a purchase from the voucher itself. Rehearsed on
TallyPrime (22 October 2026), an imported purchase without the supplier's GST
details, or without each taxed line's rates stated in the voucher, is filed
under Uncertain Transactions, whatever its masters say. With them it is
included. Tally also accepted a tax head its states rule out, and a line rate
its tax does not bear, so `accounts/gst.py` checks both first.

Whatever the company keeps in Tally, a bill whose `buyer_gstin` is another of the
client's companies' is `company_unresolved`, naming that company
(`bill_entry._addressed`): the GSTIN routes a bill, never a name it resembles. The
check reads every company in the run, and the client's companies whose PC was
disconnected at their last copy; a bill addressed to one of those holds at once,
since no reading of this run can reach its books.

For a company with GST switched on in Tally:

- **The registration.** The bill's `buyer_gstin` names which of the company's
  registrations bought; among several it is required, and must be one of them.
- **The supplier.** The voucher states the supplier's GSTIN, registration type,
  state and country, from its ledger as of the bill's date. A taxed bill whose
  supplier ledger has no GSTIN waits for review: Tally cannot claim its tax.
- **The place of supply.** As the bill prints it, else the state of the
  registration it is addressed to.
- **Tax heads.** CGST and SGST apply within one state and IGST between two. A
  bill charging the other waits for review, since a supply from a special
  economic zone, or an import, is the usual exception.
- **Each taxed line.** A Purchase's expense, freight and other-charge lines
  state their taxability, goods or services, and their rate for every duty
  head. A bill at one rate gives it to every line; at several, each line gives
  its `gst_rate`, and the lines at each rate must come to the value its tax
  lines tax.

A Debit Note states the supplier's details; an item-wise purchase does too, its
items' rates being Tally's own. After a save, the readback must show the
details as written, and carries Tally's verdict. A bill saved but not included,
such as an item-wise purchase whose stock items carry no GST details, keeps a
note saying so: its entry is sound, and its tax is completed in Tally from
GSTR-3B's uncertain transactions.

## Saving

An approved bill becomes a durable native write (`accounts/writes.py`): a
protocol 6 plan with the header, balanced lines, the identities they name, any
bill reference, and the items of an item-wise purchase.
The PC runs one `tally.write` at a time. The companion searches the bill's
invoice year for the same supplier and document number, among Purchase and
Journal vouchers for an invoice and Debit Notes for a credit note, then reports
one outcome:

- **saved**: no such voucher existed; the new one reads back exactly as approved;
- **duplicate**: Tally already has exactly this voucher, so nothing is added;
- **correction**: Tally has this bill with another date, total, ledgers or line
  amounts. The bill holds, and its reason names what differs. Nothing is overwritten;
- **attention**: a typed native hold, such as the company not being open.

Business identity is the supplier, the document number and the Indian April–March
invoice year (`vouchers.invoice_year`): supplier serials are unique within it,
whatever year the buyer's books use. A write interrupted mid-import is never sent
again; Retry save reconciles first. Bill saves use the user's own open Tally
session, and Minkops never starts, closes or restarts Tally. See
[the Windows companion](windows-app.md).

## New suppliers

When no ledger is the bill's supplier, the session sets `party.new_supplier` and
reads the supplier's GST details from the bill: GSTIN, registration type, state
and state code, place of supply, address and PIN, each with its page and quote.
The bill holds as Missing supplier. Create this ledger is offered only when:

- no ledger already has the printed name or GSTIN;
- the GSTIN passes its check character, and the printed state and state code
  match it;
- the supplier, the company and the place of supply are in one state (a
  cross-state supplier is created by hand in v1), and a Composition supplier
  charges no tax;
- every detail is quoted from the bill, with a six-digit PIN;
- the company has a Regular GST creditor to model the ledger on;
- the bill passes every other check once the supplier exists.

A person's decision queues `tally.supplier`. The companion imports the ledger
only when no ledger has its name, so a retry reads back the one it created. The
readback must show exactly one creditor under Sundry Creditors carrying every
approved statutory and mailing value. The bill is then checked again with the
new supplier and written. Other bills of the same supplier in the run are
proposed with it too, and wait for review.

## Verification

- `platform/tests/test_bill_entry.py` runs bills end to end on PostgreSQL with
  scripted sessions calling the real tools.
- `test_bill_vouchers.py` and `test_vouchers.py` pin the gate and the receipts.
- The companion's tests cover the writer and supplier creation.

Live checks use the [five-company rehearsal](tally-rehearsal.md) and the
PR Infra UAT pack, recorded in [the rebuild evidence](rebuild/evidence.md).

A labelled fixture package holds `bills/*.pdf` and `evidence/expected-bills.json`.
Select only `bills/` as inputs; the answers never reach a model.
`scripts/bill_entry_fixtures.py` grades each input of a finished run as correct,
an unnecessary hold, a wrong reason, a wrong save or a missed exception. The last
two are critical and make the command exit nonzero. It also reports the timings
and tokens. Use `--dry` for an All outputs run graded before saving, and `--rerun`
when the inputs were already saved and every new bill should now be a duplicate.
Educational Tally accepts only voucher dates on the 1st, 2nd and 31st; a correct
bill held solely for its date passes.

```sh
uv run --all-packages python scripts/bill_entry_fixtures.py score RUN_ID packages/<package> [--dry|--rerun]
```
