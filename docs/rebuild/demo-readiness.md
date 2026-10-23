# Demo readiness and learning loops

The plan for the Accounts desk's next change, agreed on 23 October 2026, and the
evidence behind it. It is written to be executed without the conversation that
produced it: each workstream says what is wrong now (with file references), what
to build, which tests prove it, and how it is accepted live. Deployment follows
it, by the [cut-over runbook](cutover.md), only when the owner asks.

- **Branch:** everything on `accounts-desk/demo-test`, this plan included, was
  merged into `staging` on 23 October 2026. Execute the plan on a new branch from
  `staging`, such as `accounts-desk/demo-readiness`.
- **Versions now:** Bill entry 1.8.0, Statement entry 1.5.0, companion 0.11.4
  (plan protocol 7), sessions on `gpt-6-luna` at medium reasoning effort on the
  provider's default tier.
- **Tests now:** 332 platform tests (425 subtests), 89 API, 131 companion and
  Windows app, 24 web unit and 15 browser; lint and ruff clean.

## How to work this plan

- One workstream at a time, in the [order](#order-and-dependencies) below. Each
  slice is test-first, one commit, pushed when its suites pass (the
  [working agreements](README.md#working-agreements) apply: no tool or assistant
  attribution in commits or PRs, PRs only into `staging`).
- Fix causes, not test documents. Never tune instructions or checks to a pack's
  bills or answer keys. The client's books, history, memory and rules decide
  ledger choice; an answer key that disagrees with the books is not ground truth.
- Real client files stay outside git (`~/minkops-private/fixtures/`), and their
  identifiers stay out of docs, commits and logs. The synthetic test pack
  (`Tally_Test_Pack_2026-10-22`, kept in the owner's Downloads) holds its answer
  keys in `Review_Only/`, which must never reach a model.
- The local stack, Tally relay and Minkops Dev setup are described in
  [Continue on Windows](README.md#continue-on-windows). Start Minkops Dev from the
  Start menu or `explorer.exe`, never from an agent's shell
  ([Windows app](../windows-app.md#build-and-run)). Local Tally is Educational:
  only vouchers dated the 1st, 2nd or 31st save.

## Where things stand

### Fixed on 23 October 2026

Each was found in a live run, fixed at its cause test-first, and pushed.

| Area | Fix | Commit |
| --- | --- | --- |
| PC identity | A PC kept its identity when its saved credential could not be read; one Windows user on one PC is one PC record (machine-derived installation ID); a connected PC moves its record to it once; companion state stays out of the roaming profile | `47e2aec`, `ed7798d`, `023d509`, `8d02a63` |
| Books left on a disconnected PC | A run names the PC a client's books left, and how to continue them | `fd51af0`, `245eb57` |
| Model settings | Back to medium effort on the default tier: high effort on the fast tier was no more accurate or faster, and cost more | `3ff2fe7` |
| Bill dates | A date must agree with the date the session quoted and be plausible, or it is read again; the answer says the date is year-first | `bc24e50` |
| Copies | A bill's copies in other files name each other whatever their status | `8fe4935` |
| Input tax | Claimed only by a registered buyer the bill names | `0fad0ea` |
| Printed adjustments | Retention, withholding and deposits carried as lines or held; an advance noted for a person | `6ac798c` |
| Cost centres and GST rates | One ledger split across cost centres and GST rates (plan protocol 7, companion 0.11.4) | `d2fc16b` |
| Every fault | Every faulty line named at once; a bill held for its own booking question also shows what the checks find | `330c2e7` |
| Instructions | Dates, projects, item-wise history, holdbacks (Bill entry 1.7.0) | `d7ffc52` |
| Printed cost split | Recorded as a fact and carried at its printed shares, or the voucher is refused (Bill entry 1.8.0) | `4cd4e63` |
| Name search | Initials kept, so "R K Supplies" never matches "MKQA GST Supplies" | `b7a53d6` |
| Statement rows | Each answer restates its row's amount, so one under a neighbour's ref is refused (Statement entry 1.5.0) | `4b14419` |
| Transfers | A transfer's other leg is sought only in another account | `adaf42b` |

### Live runs on the local stack

Scores are judged against the answer key and, where they disagree, against the
company's own Tally history; run IDs are in the local dev database.

| Run | Input | Settings | Result |
| --- | --- | --- | --- |
| `ccf565ab` | Pack bills B01–B12 | Bill entry 1.5.0, high effort, fast tier | about 6 of 12; 7 dates misread |
| `d84e1645` | Pack bills B01–B30 | 1.5.0, high, fast | about 18.8 of 30; 7 dates misread; 4 min 45 s |
| `74bbcc88` | B01–B30 | 1.6.0, medium, default tier | about 18.1 of 30; 9 dates misread; 4 min 28 s; a quarter fewer input tokens and 43% fewer output tokens |
| `662e8ae4` | B01–B30 | 1.7.0 with the fixes | about 24.2 of 30 (81%); no date misread; 4 min 56 s |
| `2e7f474e` | Pack statement S01 (1,260 rows) | Statement entry 1.4.0 | every date and amount exact; 817 of the 820 rows the key resolves booked to its ledger, none to a wrong one; 337 of 440 review rows held; about 95 of the other 103 defensible; 7–8 wrong (5 from the initials bug, 2 from a shifted answer) |
| `949e4f86` | A client's real bank statement (1,232 rows) | Statement entry 1.4.0 | 1,209 held as other side unclear, because the synthetic books lack its payees; 18 proposed, all sound; 2 transfer holds from the transfer-pairing bug; 6 min 18 s |

Not yet seen live: a protocol 7 write saved and read back in Tally, the printed
cost split, and the three statement fixes (`b7a53d6`, `4b14419`, `adaf42b`).
Workstream 10 covers them.

### How learning works today

- **Learnt treatments.** Every verified save teaches how a supplier's bills or a
  payee's bank rows are booked, standing approvals included; a bill found already
  in Tally (`duplicate`) teaches too (`memory.learn_booking`,
  `memory.learn_routing`). A best guess is learnt unconfirmed.
- **Unattended writing.** A proposal is written without a person only with no
  review note and at least `memory.STANDING` (2) matching earlier bookings
  (`bill_entry._standing`, `statement_entry._finalize`).
- **Precedent.** Bills count the client's own Tally history as precedent, and
  memory's confirmed uses, whichever is larger (`bill_entry._precedent`, lines
  627–658). Statements count only routings learnt from Minkops saves
  (`statement_entry._precedents`).
- **Practice.** Eight deterministic probes run after every sync and settle a
  company's practice from 10 or more vouchers, or ask one question per company,
  once; the answer releases what waited (`practice.py`).
- **Bank layouts.** Declared once per format, proven by running balances, then
  read with no AI call (`statement_layouts.py`).
- **Self-correction.** A Tally edit to a voucher an entry was learnt from demotes
  it; an entry whose ledgers are missing for three syncs retires
  (`memory.revalidate`, lines 197–256).
- **Rules.** Plain text written by people, up to 30 per client, read in full
  every session and cited by ID.
- **Use.** In the last three runs, 90–100% of sessions consulted rules, memory,
  practice and history, and followed the confirmed bookings and rules that
  existed.

### Gaps this plan closes

- Review cannot correct a booking. Bills offer approve, do nothing, recheck, best
  guess and create this ledger; statements approve, do nothing, recheck and
  settle (`bill_entry.OFFERED`, `statement_entry.OFFERED`, `holds._CATALOG`). A
  wrong ledger can only be refused or fixed in Tally, and memory learns only from
  approved Minkops saves, so the mistake returns every run.
- "Which ledger?" holds (`supplier_unresolved`, `classification_uncertain`,
  statement `ledger_unresolved`) carry their candidates only as free text.
- Recheck reads the run's pinned books (`desk_tools.ready` pins once, line 106),
  so a ledger created in Tally after the run started is never seen; a deferred
  bill offers no action at all (`bill_entry._offered`).
- "Create this ledger" shows only what the bill prints, and the companion writes
  every new supplier under Sundry Creditors with bill-by-bill off
  (`connectors/desktop/src/tally.js`, lines 39, 101, 130). Statements cannot
  create or choose a ledger.
- A Tally edit to a saved voucher demotes what was learnt but discards the
  corrected treatment. A held or deferred bill a person enters by hand in Tally is
  never reconciled; submitted again, it is proposed as new and only the write-time
  check finds it.
- A run's uploads travel in one request capped at 30 MB (`files.py`, line 22),
  and a bill run is capped at 40 MB in all (`bill_entry.MAX_BYTES`): the 50-bill
  pack (47.25 MB) cannot start.

## Decisions agreed

1. **Learn where people already act, or where the books already show the
   answer. Never ask for an approval just to teach.** The bar for unattended
   writing stays: two confirmed bookings, no review note, and a Tally edit
   demotes.
2. **Best guess goes.** Choose and approve replaces it: the reviewer decides the
   treatment instead of accepting the AI's held one.
3. **Recheck stays, and refreshes the books first.**
4. **Ledger creation shows and edits what Tally will get,** beside what the bill
   prints, and creates only party ledgers: suppliers for bills; the other side of
   a bank row for statements, where choosing an existing ledger is the default.
   Expense heads, tax ledgers and bank ledgers are never created by Minkops.
5. **A bill already in Tally is found when it is proposed,** not after a
   pointless approval; the write-time check stays as the final guard.
6. **Tally edits teach the corrected treatment.** A changed supplier teaches
   supplier recognition instead, with safeguards.
7. **One correction applies to the run's other bills or rows** of that supplier
   or payee, approved together in one click; the bar is unchanged.
8. **Statements count the client's Tally history as precedent,** as bills do.
9. **Mature memory steers:** departing from a treatment confirmed twice needs a
   stated reason, and then goes to a person.
10. **Uploads go in batches** under the per-request limit, committed atomically;
    the run's byte total is replaced by per-file and count limits.

## Workstreams

### 1. Recheck refreshes the books

- **Now.** `bill_entry._recheck` and `statement_entry.decide` (retry) requeue the
  item on the run's pinned mirror; `desk_tools.ready` pins every company once.
  `destination_changed` offers only Do nothing ("start a new run"). A deferred
  bill offers nothing.
- **Build.**
  - Recheck queues a sync of the record's company on its PC (`sync.queue`, reason
    `recheck`), and the item waits on that PC's sync blocker.
  - The run drops that company's pin; `desk_tools.ready` pins any company missing
    from `run.pins` to its latest published version once no sync for it is
    pending. Proposals already made keep their plans: every write verifies its
    ledgers against live Tally.
  - Offer Recheck on `destination_changed` (both workflows) and on a deferred
    record, so "do nothing, fix it in Tally, recheck" works.
  - A PC that is offline keeps the item waiting with its reason; a stopped run
    offers no recheck.
- **Tests.** `test_bill_entry.py`, `test_statement_entry.py`: a ledger published
  after the run pinned is found by a recheck, the run's pin advances, another
  record's proposal is untouched; a deferred bill and a `destination_changed`
  hold recheck; an offline PC waits.
- **Accept.** Live: create a ledger in Tally for a held bill, recheck, and the
  bill is proposed with it.

### 2. Best guess goes (lands with workstream 3)

- **Remove.** `holds._INTERPRETATION`'s `guess`; `bill_entry.OFFERED`, the guess
  branch of `decide`, `GUESSED`, `GUESSED_BOOKING`, guess candidates in
  `_offers`, `proposal["guess"]`; `memory.learn_booking(guessed=…)` and the
  `unconfirmed` status; labels in `Memory.tsx` and `progress.ts`; `docs/bill-entry.md`
  and the two mentions in the bill skill; the guess cases in `test_bill_entry.py`
  and `test_holds.py`.
- **Migration 0036.** Existing `unconfirmed` entries become `demoted` (both keep a
  booking under review); the status leaves `memory_entries`' check constraint.
- **Why with 3.** "Ledger unclear" must never lose its only path to a write.

### 3. Choose and approve

- **Answer contract.** The bill and statement `exception` gains `candidates`:
  the ledgers the session weighed (references, resolved to GUIDs and stored), for
  `supplier_unresolved`, `classification_uncertain` and `ledger_unresolved`.
  Bill entry 1.9.0 and Statement entry 1.6.0 carry the schema change.
- **Decision.** A new action, Choose and approve (`choose`), on every proposed
  record and on held interpretation codes.
  - Bills: detail names the supplier ledger, the voucher type and each line's
    ledger. Statements: the counter ledger and voucher type.
  - The server rebuilds the proposal with those GUIDs and runs every gate
    (`vouchers.check`, `statement_entry` resolution). On a pass it approves and
    writes; on a refusal it answers the gate's reason and changes nothing.
- **Ledger picker.** `GET /api/tenants/{slug}/records/{id}/ledgers?role=&q=`,
  from the run's pinned mirror, tenant-scoped: party roles from the Sundry
  Creditors (or Debtors) tree, expense roles from purchase, expense and asset
  groups, a bank row's counter from every ledger but its own bank; the session's
  candidates first, at most 20.
- **Learning.** A chosen, verified save is a confirmed booking or routing with
  evidence kind `choice` and its actor. A supplier chosen for
  `supplier_unresolved` also teaches supplier recognition (5d).
- **The run's other copies.** After a chosen save, the run's other records of
  that supplier or payee (held for the same reason, or proposed with a departure
  note) are proposed again with the chosen treatment, noted "Booked as you chose
  for …". One click, Approve N booked this way, approves them; the note keeps
  standing approval from writing them unseen.
- **UI.** `RunReview.tsx`: a form showing the voucher as it will be written, the
  candidates, a search, and a ledger choice per line (bills) or for the counter
  (statements).
- **Tests.** Choosing on each hold code saves and learns confirmed; a choice the
  gates refuse says why and changes nothing; the run's other copies are proposed
  again and approved together; the picker never leaves the tenant or the company;
  `RunReview` browser spec.
- **Accept.** Live: on B02 (a supplier whose history the session departed from in
  all four runs), choose the historical head; the next run proposes it unprompted.

### 4. Create this ledger, in Tally's terms

- **Now.** `bill_entry._supplier_plan` builds a supplier plan from the bill, and
  `supplier_gst.creation_plan` copies one same-company Regular creditor's GST and
  mailing shape. The review shows only the bill's printed details
  (`bill_entry.detail`, `RunReview.tsx` line 176). The companion's
  `createSupplier` fixes the group and bill-by-bill setting, and
  `_created_master` requires Sundry Creditors.
- **Ledger plan (companion 0.11.5, plan protocol 8).** A general `ledger` plan
  replaces the `supplier` plan in the same slice:
  - Name; Under (a group that resolves, through the mirror's group tree, to an
    allowed base: Sundry Creditors for bills; Sundry Creditors, Sundry Debtors or
    Loans & Advances (Asset) for a bank row); Maintain balances bill-by-bill, and
    its default credit period (0–365 days); Mailing Details (address, state,
    country, pincode); GST Registration Details (registration type, GSTIN).
  - Defaults: the bill's printed details, the company's creditor template, and its
    `billwise` practice: Maintain balances bill-by-bill starts as most of the
    company's existing suppliers have it (the probe's `share`). A company with no
    supplier yet has nothing to follow, so the form starts with the setting
    unchosen and the person picks it once.
  - Server validation: the GSTIN's check character and state code, a name no
    ledger already has, the group, the credit period.
  - The companion writes exactly these fields and verifies each on readback
    (GUID, group, bill-by-bill, credit period, mailing, GST). The server sends a
    ledger plan only to a companion reporting protocol 8; older ones are asked to
    update.
- **Bills.** Create this ledger opens a form laid out like Tally's ledger
  creation, editable, beside what the bill prints, and below it the bill to be
  entered with it: voucher type, each line's expense head (chosen from existing
  ledgers with the picker), cost centres and amounts. One approval creates and
  verifies the ledger, then enters the bill; it teaches the booking and the
  supplier recognition.
- **Statements.** A row held as other side unclear offers Choose and approve
  (default) and Create this ledger. The company's books decide what is offered,
  through the sync's `bank_payments` probe (`practice.py`), extended to record
  which groups its bank vouchers' counter ledgers sit under and in what share:
  - When the company books such payments to one ledger with cost centres (for
    example every worker's payment to one wages ledger, each worker a cost
    centre), the form offers that ledger first, and the payee gets no ledger of
    its own.
  - When it books them to each party's own ledger, Create this ledger is offered
    with the payee as the narration prints it, and Under lists only the groups
    the company already uses for bank counterparties, most used first, within a
    safe list: Sundry Creditors, Sundry Debtors, Loans & Advances (Asset) and
    Current Liabilities, and their sub-groups. Bank, tax, capital, stock and
    expense groups are never offered.
  - Books too new to tell offer the safe list with nothing preselected, beside
    the probe's existing one-time question.

  The person confirms or edits the choice before approving, and the server
  refuses a group outside the safe list.
- **Never created.** Expense heads (chart-of-accounts decisions), tax ledgers
  (statutory setup) and bank ledgers. A bill or row needing one holds with that
  reason; once it exists, Recheck (1) finds it.
- **Tests.** Plan defaults and validation (`test_bill_entry.py`,
  `test_supplier_gst.py`, statement tests); the extended `bank_payments` probe
  and the bill-by-bill default (`test_practice.py`); companion XML, readback and
  version gating (`connectors/desktop/tests`); the form's browser spec.
- **Accept.** Live: B09's new supplier created with bill-by-bill on and a credit
  period, verified in Tally, and the bill entered; a bank row's payee created
  under the chosen group.

### 5. Learning from Tally

- **5a. Edits to saved vouchers.** In `memory.revalidate`, where `_rebooked`
  demotes, also read the voucher's current treatment from the mirror and record it
  as confirmed, with evidence `{kind: "tally_edit", voucher, alter_id}`, once per
  alteration:
  - a bill: its voucher type and expense heads, which are its ledgers less the
    supplier, those under Duties & Taxes and the round-off; item-wise when it has
    stock lines;
  - a bank row: its counter ledger, the voucher's ledgers less the bank's, and
    its voucher type.

  Amount-only edits change nothing; a deleted or cancelled voucher demotes only; a
  changed supplier demotes and teaches recognition (5d).
- **5b. Bills and rows entered by hand.** After each published sync (beside
  `memory.revalidate` in `sync.py`, line 442), match the company's held and
  deferred records in runs under review:
  - bills by document identity (supplier, number in the company's
    `invoice_number_field` fields, invoice year; `vouchers.document_identity`),
    with the supplier found by the printed GSTIN when no ledger was chosen;
  - bank rows only by the row's reference or UTR in the voucher, with the amount,
    on the statement's bank ledger within three days.

  A match becomes `duplicate` with the voucher as `current`, noted "Entered in
  Tally by hand", and teaches the voucher's treatment as confirmed (evidence
  `tally_entry`).
- **5c. Already in Tally at proposal.** In `bill_entry._propose_one`, after the
  checks, look the identity up in the pinned mirror: an identical voucher makes
  the bill `duplicate` at once and teaches its treatment; a different one holds it
  as `already_in_tally` (final), naming what differs. Bank rows, only on a
  reference or UTR match. The write-time duplicate check is unchanged.
- **5d. Supplier recognition.** A memory kind `supplier_name`: the printed name
  (normalized) and GSTIN when printed, mapped to a supplier ledger. Learnt when a
  person chooses (3) or creates (4) the supplier, or edits a saved voucher's
  supplier (5a), only when the name is in the session's own evidence quote and no
  printed GSTIN conflicts. `find_ledger` lists it first, marked as learnt; a later
  different choice demotes it. It never affects how a bill is booked.
- **Tests.** `test_memory.py`, `test_sync.py`, `test_bill_entry.py`,
  `test_statement_entry.py`: an edit teaches once; amount-only, cancelled and
  party edits behave as above; a held and a deferred bill entered by hand
  reconcile; identical and different copies at proposal; recognition only under
  its safeguards.
- **Accept.** Live, on Tally: edit a Minkops-saved voucher's ledger, sync, and see
  the corrected entry confirmed in Memory; enter a held bill by hand, sync, and
  see it reconciled.

### 6. Statements count Tally history as precedent

- **Now.** `statement_entry._precedents` counts only routings learnt from Minkops
  saves, so every payee needs two approved Minkops saves before unattended
  writing.
- **Build.** Count the bank ledger's vouchers of the last 400 days whose counter
  ledger and voucher type match and whose narration contains the payee (the
  four-character containment `memory.entries` uses); precedents are the larger of
  that count and memory's uses, as for bills.
- **Tests.** Two such vouchers in history give precedent 2 and standing approval
  under `only_exceptions`; another counter ledger, or a payee under four
  characters, counts nothing.

### 7. Mature memory steers

- **Build.** When a supplier or payee has a confirmed treatment with at least
  `memory.STANDING` uses and a proposal departs from it with no cited rule, the
  proposal needs a `departure` (a new nullable answer field: the handwritten
  instruction, rule or printed fact that justifies it). Without one it is refused,
  naming the learnt treatment; with one it is proposed with the reason as a review
  note, never written unattended.
- **Tests.** Refused, then accepted with a reason and noted; no effect below the
  threshold or with a cited rule.

### 8. Uploads in batches; run caps

- **Why the caps exist.** The 30 MB cap (1 October, the first Accounts commit)
  bounds one request: a source's whole file set travelled in one request, read
  into memory, on an API that runs on Cloud Run with 1 GiB, concurrency 2 and a
  60 s timeout ([infra](../../infra/README.md)), whose requests are limited to
  about 32 MiB. The companion's folder snapshot shares it (with a 42 MB edge
  limit for its base64 receipt). The 40 MB run cap (21 October) has no recorded
  reason; its predecessor, 8 MB, matched a provider limit when a run's files were
  sent together, which per-file sessions no longer do.
- **Build.**
  - Migration 0035: `account_uploads` (tenant, id, source, actor, created,
    committed) and `account_files.upload_id`.
  - `POST /api/tenants/{slug}/accounts/sources` takes `upload_id` and `final`:
    batches stage files not current; the final batch validates the whole set (at
    most 100 files, unique paths, 5 MB each) and makes it current atomically. An
    abandoned upload leaves nothing current. The per-request cap stays.
  - The console (`LaunchRun.tsx`) sends batches under 25 MB.
  - Bill and statement launches drop the byte total, keep the file count and
    per-file size, and read sizes with `octet_length`, never the contents.
  - Messages name what the person did ("Upload…"), never "source refresh".
- **Not now.** The companion's single-snapshot folder refresh
  (`desktop.py`, line 549; `connectors/desktop/src/index.js`, line 87): neither
  run form uses connected folders. Confirm that before deferring.
- **Tests.** API: three batches commit atomically; an abandoned upload and
  another user's upload are refused; bill launch takes 50 files of 1 MB. Browser:
  LaunchRun batches.
- **Accept.** Live: the 50-bill pack starts and finishes within 10 minutes.

### 9. Versions and documentation

- Bill entry 1.9.0, Statement entry 1.6.0, companion 0.11.5 (plan protocol 8 for
  ledger plans; the minimum stays 0.11.0, with ledger plans gated).
- Update `docs/bill-entry.md`, `docs/statement-entry.md`,
  `docs/accounts-desk.md`, `docs/attention.md`, `docs/windows-app.md` (protocol 8
  contracts), the rebuild [progress](README.md#progress), [evidence](evidence.md)
  (23 October runs), and [cutover.md](cutover.md) (companion 0.11.5, signed).

### 10. Acceptance runs

On the local stack, Review mode `all_outputs` unless noted, scored as in the
[appendix](#appendix-scoring-a-run):

- **Bills.** The pack's B01–B30, then B01–B50 after workstream 8. Expect every
  date, total, company and supplier as printed; no proposal eligible for
  unattended writing with a wrong treatment; 50 bills within 10 minutes.
- **Statements.** S01 and S02 and the client's real statement. Expect no date or
  amount mismatch, no shifted answer, the R K Supplies rows not booked to another
  creditor, no transfer held for a same-account pairing.
- **Protocol 7 in Tally.** Approve B11 (a 60/40 split, on a ledger keeping cost
  centres) and B03 (one head at three GST rates) and check each saved voucher in
  Tally.
- **Learning loops.** The live checks in workstreams 1, 3, 4 and 5.
- **Standing approval.** Rerun the 30 bills under `only_exceptions`; list what was
  written unattended and verify each in Tally.

## Order and dependencies

1. Workstream 1 (recheck), then 2 and 3 together (best guess out, choose in).
2. Workstream 5a–5c (learning from Tally), then 5d (needs 3).
3. Workstream 4 (needs 3's picker; ships companion 0.11.5).
4. Workstreams 6 and 7.
5. Workstream 8 (independent; may run any time before acceptance).
6. Workstreams 9 and 10, then the deployment preconditions below.

## Deployment readiness

Deployment is the owner's call, by [cutover.md](cutover.md). Before it:

- The manual testing list in [progress](README.md#progress), and workstream 10,
  pass on the local build.
- **Instance tier.** `minkops-books` uses the same entry tier as Myndral's Cloud
  SQL instance (about US$15 a month). Read the exact tier name from Myndral's
  instance settings and record it in the runbook before provisioning.
- **Retention and terms.** A retention and deletion policy for mirrored books
  (India's DPDP Act) and the terms of service are an open To Do for a later
  sprint, by the owner's decision on 23 October 2026. They no longer block the
  cut-over, and stay listed until done.
- Companion 0.11.5 is packaged signed with the organization's certificate and
  recorded in `windows-release.json`; the runbook names 0.11.5.
- **History.** 43 commits on this branch carry an assistant `Co-Authored-By`
  trailer that the working agreements forbid (22 from 21 October, 21 from 23
  October), and two early diffs hold a real-looking Windows hostname. The owner
  decided on 23 October 2026 to leave that history as it is. Commits and PRs
  from here on carry no assistant attribution.
- Before any merge into `staging`, park and push `backup/staging-pre-<issue>`.
  After it, delete branches already merged into `staging`, and a `platform/*`
  branch once it is verified to have drifted far from `staging`.

## Not in this plan

- A supplier debit note whose base invoice is not in the books (B25): booked as a
  Purchase today; a review note is wanted later.
- Instalments and credit periods printed on a bill (B27).
- Line discounts on item-wise purchases (booked at a net rate).
- Mixed item-wise and accounting history on one ledger, beyond the instruction
  fix.
- The companion's folder-refresh batching (see workstream 8).
- Admins disconnecting a member's PC (deferred on 22 October).
- Wage batches beyond holding them.
- The local Windows build script reports success when packaging fails; it lives
  outside the repository. Moving it into `scripts/` with size and exit checks is
  worth doing before the signed build.

## Owner's decisions (23 October 2026)

1. **History.** Leave the committed history as it is; no assistant attribution in
   future commits or PRs.
2. **A bank row's other side.** Inferred from the company's own books by the
   extended `bank_payments` probe, within a safe list of groups, and confirmed or
   edited by the person in the form ([workstream 4](#4-create-this-ledger-in-tallys-terms)).
   Whether a worker gets a ledger of their own follows how the company books such
   payments.
3. **Bill-by-bill for a new supplier.** Follows most of the company's existing
   suppliers; with no supplier yet, the person picks it once in the form.
4. **Branches.** Delete those already merged into `staging`, and a `platform/*`
   branch once the merge has succeeded and its drift from `staging` is verified.
5. **Instance tier and retention.** Myndral's entry tier; the DPDP retention
   policy and terms of service are a To Do for a later sprint.

## Appendix: scoring a run

- **Bills.** Join `run_records.facts->>'file'` to the key's `File`
  (`Review_Only/bill_scenarios.csv`, details in `expected_results.json`). Score
  what the document determines (date, total, company, supplier, number, taxes)
  against the key; score outcome and ledger against the company's history,
  memory and rules, using the key's expectation where they agree. Check the PDFs
  where the key and the bill differ (render pages with `pypdfium2`).
- **Statements.** Join `facts->>'reference'` to the key's `Reference`
  (`Review_Only/bank_reconciliation_key.csv`). Count rows the key resolves that
  were booked to its candidate and family, rows it sends to review that were held,
  and judge the rest by narration and history.
- **Unattended exposure.** A proposal with no review note and
  `checks.precedents >= 2` would be written under `only_exceptions`; list them
  and check each.
- **Tally.** Read-only XML exports through the local relay (`127.0.0.1:9000`)
  confirm masters, cost-centre flags and history; never write to Tally outside an
  approved save.
