# Rebuild evidence

This page holds the facts behind the [rebuild decisions](README.md). Everything here was checked on 21 October 2026, against the code on this branch, the installed SDK, the sample client files, or public sources.

## Legacy retirement (branch `maintenance/retire-legacy-paths`)

The branch has eight commits on top of `2781c60`:

| Commit | What it did |
| --- | --- |
| `5ff66bd` | Retired the pre-0.14 fixed-field bill contract |
| `01d78d7` | Retired the fixed-field companion writer and protocol-4 companions (minimum companion is now 0.9.0) |
| `6292616` | Removed the Excel bill destination and the launch voucher-type picker (Bill Entry 0.18.0, migration `0018`) |
| `bbe7d83` | Plans every statement row as a protocol-5 voucher |
| `fccd85e` | Stopped deriving purchase voucher-type offers that nothing read |
| `023396f` | Migration `0019`: stops unfinished runs still pinned to removed contracts, and pins the runtime binding the code used to infer |
| `2d6c429` | Dropped a test hook left behind by the Excel retirement |
| `f16048c` | Brought the docs in line with the Tally-only bill contract |

Line counts are of tracked source files, counted with the same script at both commits:

| Area | Before | After | Change |
| --- | ---: | ---: | ---: |
| `platform/src` | 12,004 | 10,069 | −16% |
| `platform/src/minkops_platform/accounts` | 6,965 | 5,173 | −26% |
| `connectors/desktop/src` | 2,208 | 1,784 | −19% |
| All source | 26,325 | 23,503 | −10.7% |
| All tests | 16,285 | 14,667 | −9.9% |

Test counts went from 682 to 617 for Python, 136 to 108 for the companion, and 57 to 51 for the web app. Before you deploy anything from this branch:

1. Run migrations `0018` and `0019`.
2. Reinstall the workflows.
3. Confirm every registered PC reports companion 0.9.0 or later.

## Why the current structure fails

The [runtime review](../reviews/2026-10-21-bill-entry-runtime-review.md) found these problems in a live run:

- **Stages ran one after another.** Routing took 122.7 s, the posting pattern 250.4 s, and each bill session 200–440 s.
- **Environment preparation** added 28–41 s for each stage that was measured.
- **A lost wake-up stalled the run.** After the pattern was confirmed, posting work started about 18 minutes late (P0).
- **A decision came back as an error even though it had been saved.** The user saw a 504 and then a 409 (P0).
- **Status polls were huge.** The response reached 16.5 MB because the discovery copy in run config is about 17 MB.
- **Small writes were slow.** One flag update took 57 s, because it rewrote that config and fired triggers.
- **Memory forced a single lane.** The merge step decoded one discovery copy per child, so workers were cut to one lane. This branch's `infra/deploy_runtime.py` sets `--lanes 4` with 1 GiB.

All of these come from the structure (stages, gates, copied snapshots), not from the accounting rules.

**How many sessions the speed target needs:** sessions ≥ bills × seconds per bill ÷ 600. For 50 bills in 10 minutes, that is about 25 sessions at 300 s per bill, or about 10 at 120 s.

A dedicated database doesn't change this arithmetic; it is chosen to isolate client books and to give more connections. Today, `infra/deploy_runtime.py` uses the shared instance `myndral-prod:us-central1:myndral-db`. `infra/README.md` gives the runtime role 16 connections and budgets CAD 8 of the CAD 20 monthly envelope for Minkops' half of that instance.

## Code facts the design relies on

### Function and MCP tools in the installed OpenAI SDK

These files are under `.venv/.../openai/types/beta`:

- **Tool types.** `agent_tool_param.py` defines a `function` tool (name, description, parameters, `defer_loading`). It also defines an `mcp` tool with `server_label`, `transport`, `connection_origin` (`service` or `environment`), `credential_id`, `allowed_tools`, `request_metadata` and `required`. Two more tool types are `tool_search` and `programmatic_tool_calling`.
- **Passing tools to a session.** `agents/session_create_params.py` takes them as `tools`.
- **Pausing for a tool call.** `agent_session_requires_action_event.py` emits `agent.session.requires_action`. `AgentSession` has `required_actions` and a `requires_action` status, so pending calls survive a worker restart.
- **Answering a tool call.** `agent_session_input_param.py` defines `agent.session.input.tool_result`, with `call_id`, `success` and `turn_id`.
- **What the adapter did before slice 3.** `platform/src/minkops_platform/runtime/openai_hosted.py` called `sessions.create(agent, environment, input, stream=True)`, passed no tools, and re-attached to a dropped stream up to three times. That hosted-environment path (`execute`) still serves the old runs until cut-over. Tool sessions (`run_tool_session`) sit beside it.
- **Errors inside a stream.** `_streaming.py` raises an SSE `error` event as a plain `APIError` instead of yielding it. Transport failures arrive as `APIConnectionError` or `APITimeoutError`. The driver treats all three as an interrupted stream and reads the session's own state on the next attachment.

### The tool loop, measured live (21 October 2026)

These were measured with `gpt-6-luna` through the installed SDK, using tiny prompts:

- **A session needs no execution environment.** With `environment: {"type": "none"}` and function tools, a turn runs as follows:
  1. `created` and `turn.created`;
  2. `turn.item.added` with a `function_call`;
  3. `requires_action`, waiting for the answer;
  4. the answer, sent as `agent.session.input.tool_result` through `sessions.events.create`;
  5. `turn.completed`, then `idle`.
- **A pending call survives a dropped stream.** After the worker stopped reading at the first function call, `sessions.retrieve` reported `requires_action`, with the call in `required_actions`. Answering it and re-attaching with `sessions.events.stream` continued the turn to completion. The re-attached stream re-delivers items already seen, so answers must be deduplicated by call ID.
- **Session creation is not idempotent.** A second `sessions.create` carrying the same `Idempotency-Key` header started a new session.
- **Input comes with creation.** Creating a conversation-only session without input is refused with 400 "conversation-only sessions currently require initial input". The SDK's two-step `sessions.stream` helper therefore does not apply.
- **A lost creation can be found again.** A session waiting on a call is listed by `sessions.list(order="desc", limit=100)` with its metadata; 100 is the largest page. So a creation whose response was lost is found by its item metadata, never by creating another session.
- **Images read from data URLs.** A scanned page sent as an `input_image` data URL was read correctly: the model returned the synthetic bill's invoice number.
- **Usage comes late.** Neither `turn.completed` nor its `turn` carried usage. The turn's own record reported it 4.4 s later, and the session's soon after.
- **A repeated answer is accepted silently.** After a call was answered, sending its `tool_result` again was accepted with no error and no new turn, with the same idempotency key or a new one. So the driver answers only what `retrieve` lists as pending.
- **Sessions linger, then expire.** A completed conversation-only session was still listed five minutes later. Sessions from the morning's probes were gone (404) by the afternoon.
- **Each model call carries the agent's base instructions.** They are about 7,800 tokens, mostly cached after the first call. A one-call reply used 7,828 tokens; a bill-shaped turn with two tool calls (three model calls) used 23,846 input and 87 output tokens.
- **The lanes work end to end.** One bill-shaped item ran through real lanes on PostgreSQL with `gpt-6-luna`:
  - both calls were logged and the proposal recorded;
  - the run moved to review;
  - the closer recorded the usage and deleted the session.

  The session took about 20 s.

### Identity and duplicates

- **Statement tokens include the tenant UUID.** They are `uuid5(NAMESPACE_URL, f"minkops:{tenant_id}:{key}:{identity}")`, built in `accounts/tally_writes.py` (around line 174) and `accounts/statements.py` (around line 90).
- **Tokens are written into the Tally narration** as `[Minkops <kind>:<uuid>]` (`connectors/desktop/src/voucher.js`, the `tag` regex and the `importBody` narration prefix).
- **Why a fresh start can't double-post.** `voucher.js` (around line 296) applies these rules in order:
  1. A voucher carrying the plan's own tag is recognised as a duplicate.
  2. Any other voucher on the same date with the same bank-ledger amount holds as `possible_existing`.
  3. For Contra, a single tagged covering voucher is a duplicate; any other covering voucher holds.
- **Bills never depend on tenant IDs.** They match by party and document number in the client's number fields.
- **Statement row identity is** `row_identity` in `connectors/src/minkops_connectors/statement.py` (around line 51): reference, date, amount, balance, occurrence.

### Companion and installer

- **Duplicate-company guard.** `openCompanyScope` in `connectors/desktop/src/tally-session.js` refuses two open companies that share a name or a GUID. When only the GUID repeats, its message names the first company, which is wrong.
- **Per-user install.** `apps/windows-app/package.json` builds NSIS with `oneClick: false` and `perMachine: false`.
- **Port per PC.** The Tally port is already set per PC and carried into every plan (`plan.port` in `tally.js`, `config.port` in `client-context.js`).

### Windows checkout

- **Line endings.** There is no `.gitattributes`. CRLF conversion changes the bytes that migration checksums (`db/migrate.py`) and the archived-migration hashes in `db/tests/test_branch_upgrade.py` are taken over.
- **File encoding.** The Python version is 3.12. On Windows, `Path.read_text()` without an encoding uses cp1252, so set `PYTHONUTF8=1`.

## PR Infra samples (aggregates only)

The three files shared on 21 October are not in git:

- one ICICI "Detailed Statement" XLSX for September 2026;
- two scanned March 2026 supplier bills.

This section records only structure and counts. Account numbers, GSTINs, names and amounts are left out on purpose.

### Statement

- **Layout.**
  - One sheet, with about 15 metadata rows above the header (row 17).
  - Columns: serial number, transaction ID, value date, transaction date, posted date-time, cheque/reference (empty on every row), remarks, withdrawal, deposit, balance.
- **Values are text.**
  - Amounts use Indian digit grouping (`12,34,567.89`).
  - Dates use three formats: `01/Sep/2026`, `01/09/2026` and `01/09/2026 11:17:47 AM`.
- **Footer.** The rows end with a page total, opening balance, total withdrawals, total deposits and closing balance, then a legend.
- **Two independent proofs hold.**
  - All 1,232 transactions chain exactly on the running balance (1,203 withdrawals, 29 deposits).
  - The footer totals equal the row sums, and opening − withdrawals + deposits equals closing.
- **A filter label is not proof of a filter.** The metadata says "Transaction type: DR", yet every deposit is present, so the balances must decide completeness.
- **The account number and IFSC appear in the metadata**, so the bank ledger can be identified without AI.
- **One bank `Tran. Id` appears on two different rows.** `row_identity` stays unique because the balances differ.
- **Narration families:**

  | Family | Rows |
  | --- | ---: |
  | `INF/NEFT` | 700 |
  | `UPI` | 208 |
  | RTGS (two formats) | 130 |
  | `MMT/IMPS` | 106 |
  | `INF/INFT` | 55 |
  | `NEFT-RETURN` | 8 |
  | `BIL/ONL` (bill payments) | 6 |
  | Other (cash-management and clearing) | 19 |

  Payee names are truncated to 20 characters in RTGS, compressed in NEFT, and absent from UPI rows, which show only a payment address.
- **NEFT returns pair deterministically.** `NEFT-RETURN-<UTR>-<name>-<reason and code>` carries the original payment's UTR: 8 of 8 matched, all on the same day.
- **Payees are spread thin.**
  - 881 distinct payees across 1,203 debits; 716 of them appear only once.
  - The top 10 payees cover 8% of rows, the top 50 cover 20%, and the top 200 cover 43%.
  - Most rows look like bulk wage-style NEFTs in round amounts. One batch-reference field repeats across many rows.
  - The remarks field often holds site codes.
  
  So booking depends on how the client books, which a probe or a question can settle, not on memory of each payee. Lookups must therefore accept many subjects per call.

### Bills

- **Both are scans.** Each PDF has two JPEG pages, no fonts and no text layer ("OpenPDF"). Page two is the e-way bill that corroborates the invoice.
- **One bill's "Amount" column includes tax.** Quantity × rate per line rebuilds the printed taxable total, while the column itself is gross. The other bill has a goods line plus a services line (handling) on one invoice.
- **Both are e-invoices** with an IRN, an acknowledgement number and a signed QR code. If the QR payload decodes and verifies (to be checked in the slice-9 feasibility test), it pins supplier GSTIN, buyer GSTIN, number, date and total, independently of the scanned text.
- **Routing.** Both bills are addressed to a state GSTIN different from the one tied to the bank account, so company lookup must search every registration.
- **Client marks on the bills.** Each carries a receipt-register ("DMR") stamp with a number and date, a "received" signature, and a handwritten site note. The file names follow `<DMR>_<SUPPLIER>_<invoice>_<…>_<date>`.

## Tally incremental-sync research

Confidence: **[D]** documented by Tally; **[I]** seen in open-source integrator code; **[U]** unverified (inference, or lab notes from a small, very new repository).

### Sources

| Ref | Source |
| --- | --- |
| S1 | https://github.com/dhananjay1405/tally-database-loader/blob/main/src/tally.mts |
| S2 | https://github.com/dhananjay1405/tally-database-loader/blob/main/tally-export-config-incremental.yaml |
| S3 | The same repository's README, `docs/incremental-sync.md` and release history |
| S4 | https://github.com/Accounting-Companion/TallyConnector |
| S5 | https://help.tallysolutions.com/synchronisation-faq-tally/ |
| S6 | https://help.tallysolutions.com/article/DeveloperReference/faq/6191.html |
| S7 | https://help.tallysolutions.com/article/DeveloperReference/faq/6192.html |
| S8 | https://help.tallysolutions.com/edit-log-in-tallyprime-faq/ |
| S9 | https://help.tallysolutions.com/release-notes-tallyprime-2-1/ |
| S10 | https://help.tallysolutions.com/?p=191443 |
| S11 | https://help.tallysolutions.com/migrate-company-data-tally/ |
| S12 | https://help.tallysolutions.com/repair-company-data-tally/ |
| S13 | https://help.tallysolutions.com/sample-xml/ |
| S14 | https://help.tallysolutions.com/accounting-faq/ |
| S16 | https://github.com/ComplyEaze/bridge/tree/main/docs/tally |

### Findings

- **Alteration IDs.**
  - A voucher's alteration ID changes every time it is altered or re-accepted; its creation ID does not [D, S5].
  - Masters and vouchers have separate counters, `$AltMstId` and `$AltVchId`, on the Company object. The loader filters exports with `$AlterID >` the stored marker [I, S1].
  - Deletions appear to advance the counters [U, S16].
  - Nothing documents that alteration IDs only ever increase.
- **Company markers.**
  - The Company object exposes `$AltMstId`, `$AltVchId`, `$LastVoucherDate`, `$BooksFrom` and `$Guid` [I, S1, S4].
  - `ALTVCHID` is missing for a company with no vouchers, so treat it as 0 [I, S4].
  - `$CmpVchID` is the next voucher's MasterID [D, S7].
- **GUID and MasterID.**
  - MasterID identifies a voucher [D, S6, S7].
  - An object's GUID is the company GUID followed by the MasterID in hex [I, S4].
  - A backup restored on another machine keeps the company GUID [D, S5].
  - Tally's FAQ contradicts itself on whether Split Company Data gives the halves the same GUID [D, S5]. Split twins were seen sharing a GUID and `ALTVCHID` [U, S16].
  - Migrating from release 2.1 or earlier to 3.0+ moves data to a new six-digit company number [D, S11]. What happens to IDs is undocumented.
- **Deletions.**
  - Tally documents no XML or TDL access to deletions or to the Edit Log [D, S8, S9].
  - Edit Log data isn't carried by sync or import, and Repair can erase it [D, S8, S12].
  - The loader finds deletions by exporting every GUID+AlterID and deleting rows whose GUID is missing or whose AlterID has changed, then re-pulling by `$AlterID` [I, S1, S2].
  - The loader's own docs prefer a full sync as the safer option [I, S3].
- **IDs going backwards.**
  - Restoring an older company data file causes alteration-ID mismatches [D, S5].
  - Repair, migration, split company and group companies are undocumented [U].
- **Filtering and paging.**
  - Collections accept `<FILTER>` with a formula such as `$AlterID > N` [I, S1]. The official Day Book sample filters with a formula and `SVFROMDATE`/`SVTODATE` [D, S13].
  - Page large exports by counting vouchers per date and packing the dates into batches of at most 5,000 [I, S1].
  - Very large requests can freeze Tally, and batches above 10,000 can stall [I, S3].
  - A cut-off 282 MB response still reported `STATUS=1`, and Tally stayed busy after the client gave up [U, S16].
  - Tally handles one request at a time [U, S16].
- **Voucher states.**
  - Cancelling keeps the voucher number [D, S14].
  - With automatic numbering, deleting a voucher renumbers the ones after it [D, S10]. Renumbering doesn't change AlterID [I, inferred from S1].
  - Post-dated vouchers stay out of the ledgers until their date [D].
  - The loader excludes cancelled and optional vouchers [I, S2], so a change into either state looks like a deletion.

The sync algorithm in the [README](README.md#sync-algorithm) is built from these findings and marks the steps that still need the rehearsal.

### Rehearsed on TallyPrime Edit Log 1.1.7.2 (21 October 2026)

These were run on *Test Company*, one of the five synthetic rehearsal companies. The probes were ₹1.00 Journals tagged `[Minkops rehearsal]`, dated 31 October for Educational mode, and every one was deleted afterwards.

- **A delta by AlterID works.** A `Voucher` collection filtered by `$AlterID > N` returns exactly the vouchers altered since marker *N*.
- **Per-date counts need a source collection.** `BY` and `AGGRCOMPUTE` work only on a collection built from a `SOURCECOLLECTION`; on a typed collection they are ignored and every voucher comes back. A numeric day key avoids two-digit-year strings: `BY VchDay:($$YearOfDate:$Date * 10000 + $$MonthOfDate:$Date * 100 + $$DayOfDate:$Date)`. The same form with `BY All:1` gives an independent count of each master type.
- **Each creation advances `$AltVchId` by 1.** Over the whole rehearsal it rose from 74 to 86 and never reused a value.
- **Deleting a voucher removes it from collections and counts.** This held in the Edit Log edition too: it was not kept with `ISDELETED` or `ISDELETEDVCHRETAINED`. One deletion advanced `$AltVchId` by 3. A deletion therefore triggers the next delta, and the census then finds the missing GUID. Deletion through XML import (`ACTION="Delete"` with `TAGNAME="MASTER ID"`) succeeds.
- **A cancelled voucher stays in collections** with `ISCANCELLED=Yes`, and the cancellation raises its `AlterID`, so the next delta collects the change. Cancelling through XML import needs the voucher's date, type and narration in the body; a bare `ACTION="Cancel"` is refused as an empty object.
- **An optional voucher is in collections and counts** with `ISOPTIONAL=Yes`.
- **Collections with `FETCH *` carry every master field the gates read.** For ledgers that means `PARENT`, `ISBILLWISEON`, `ISCOSTCENTRESON`, `PARTYGSTIN`, the bank details and the nested GST, mailing and alias lists. Voucher types carry `RESERVEDNAME`, `ISACTIVE` and `NUMBERINGMETHOD`; stock items carry their units and GST/HSN lists. Fields left at their default "No" are omitted, unlike the "List of Accounts" export.

Still to rehearse: Split Company Data, and restoring an older backup. Both need Tally's UI and are listed for manual testing in the README.

## Statement entry, rehearsed live (21 October 2026)

These runs used the local stack: API, worker lanes, the headless companion, TallyPrime Edit Log 1.1.7.2 in Educational mode, and `gpt-6-luna`. The client business has five authorised companies. Every date is the 1st, 2nd or 31st.

**A two-bank rehearsal.** Two new formats came from Pradeepraj Infra's ICICI and HDFC accounts, with 11 rows:

- **Layouts.** `gpt-6-luna` declared both layouts, and the balances proved them.
- **Routing.** It found the company and each bank ledger by account number, across all five companies. Each other row went to its supplier, customer or charges ledger, or to the other bank for the transfer.
- **Pairing.** The transfer legs were paired through `find_transfer`, and the NEFT return was booked against the supplier it came back from.
- **Review.** The run reached review in 75 s.
- **Writes.** Write ready rows approved all 11 rows as 10 writes, one Contra covering both transfer legs. All 10 saved and verified within 27 s.
- **Independent check.** An XML export from Tally found all 10 tagged vouchers.

**The PR Infra UAT pack** (private store, `uat-2026-10-21`). The answer keys never entered a run.

| Scenario | Expected | Observed |
| --- | --- | --- |
| S01 core scenarios | Each row routed or held; split charge; both identical payments kept | 9 saved and verified; the anonymous UPI held as `ledger_unresolved`; the 118 charge split 100 + CGST 9 + SGST 9; the reversal kept in both directions; both identical 1,773 payments written as distinct siblings |
| S02 overlap | Duplicates, no extra save | 3 duplicates; no layout session needed |
| S03 broken balance | Held sheet, never clean | The saved layout was retired; relearning was refuted three times; the sheet holds as `statement_layout_changed` |
| S04 date order | One confirmation, then duplicates | One card; after the answer `dmy`, 2 duplicates of S01 |
| S05A then S05 | One "Transactions missing", rows ready | One item: closed at 97,000.00 on 31 August, opens at 107,000.00 on 1 September; rows stay proposed |
| S06 own-bank transfers | Two Contras, not four entries | 2 Contra vouchers, each covering both legs |

**Usage.** Across these 8 runs, 15 sessions used 714,350 input tokens (72% cached) and 25,119 output tokens. Of 26 native writes, 21 saved and 5 reconciled as duplicates.

**Found and fixed along the way:**

- **Write ready rows.** It hit a version conflict when approving one transfer leg approved its partner, which the action had already read. It now reads each row as it approves it.
- **Refutation messages.** A summary mismatch marks every row, so the message named a consequence. It now names the first broken balance, then the printed control.
- **Balance spans.** A row held for its ledger split a statement's chain, so its span went unrecorded. Chains are now built per statement account from every proven balance.
- **Races the tests caught:**
  - two layout items settling at once took one item ordinal;
  - two sheets in a new format proved at once collided on the profile version;
  - the last chunk's settle saw itself as unfinished and never finalized the run.

## Bill entry, rehearsed live (21 October 2026)

The same local stack as the statement rehearsal ran Bill entry 1.0, with four worker lanes and the headless companion. Runs used the All outputs review mode and inferred each bill's company.

**The PR Infra UAT bills** (private store, `uat-2026-10-21`). The answer keys never entered a run. The deployed staged build had already saved B01–B03 into this Tally company, and created B03's supplier, so these runs exercised its repeat path.

| Bill | Expected | Observed |
| --- | --- | --- |
| B01–B03, three files | No second voucher | All three proposed with their suppliers' history; approval found each in Tally: 3 verified duplicates |
| B04 and B05, together | No second voucher; the revision reviewed | The two files print different versions of one bill, so both held as `source_values_conflict` |
| B06 total off by a rupee | Held, no adjustment | `source_values_conflict`: the printed total is not the sum of the printed lines, and no round-off is printed |
| B07 unknown buyer | Company unclear, no fallback | `company_unresolved` |
| B08 31 March | Before books begin | `date_before_books`, held at once |
| B09 image-only copy of B01 | Read from the image; a duplicate | Read correctly from the scan; approval found B01: a verified duplicate |

Tally still holds exactly one voucher for each of these bills, the ones the staged build saved.

**The synthetic package for Pradeepraj Infra** (15 bills of the [five-company rehearsal](../tally-rehearsal.md)). `scripts/bill_entry_fixtures.py` scored 15 of 15 correct, with no critical outcome:

- seven new bills and the round-off bill saved and verified, in 27 s from approval;
- the historical duplicate and the scan copy of bill 01 added nothing;
- the changed version held, naming how Tally's voucher differs;
- the missing supplier, the ambiguous supplier, the date before the books and the item-wise supplier held for those reasons.

All 15 files were read in 4 min 10 s from launch across four lanes; a session took 54 s at the median and 129 s at most.

**Create this ledger** ran on Test Company with one synthetic bill from a new Rajasthan supplier. The bill held as Missing supplier, with the printed statutory details. One decision created the ledger under Sundry Creditors. Its readback carried the GSTIN, Regular registration, state, place of supply, address and PIN. The bill was then saved as one Purchase.

**Usage.** Seven bill runs used 31 sessions: 3,108,360 input tokens (79% cached) and 91,088 output tokens. That under-counts three rechecked bills, whose second attempt replaced the first's usage (noted for slice 12). Of 19 native writes, 10 saved (one of them the supplier), 7 reconciled as duplicates and 2 held.

**Found and fixed along the way:**

- **History lookups returned nothing.** `party_history` matched ledger names, but sessions passed the GUIDs `find_ledger` returns, so every supplier seemed to have no history. It now takes either, names any subject that is no ledger, and shows each voucher's stock items.
- **Item lists read as inventory.** The skill told sessions to hold "item-wise entries", so ordinary invoices listing goods with HSN codes and quantities held. Only a client that books such purchases item-wise now needs stock items. Tally's "inventory values are affected" flag is no signal: every purchase head in the rehearsal companies carries it, and their history is booked to ledgers.
- **Gaming a review note.** Told that a proposal booked unlike the supplier's history would go to review, a session rebooked a sound bill to the historical ledgers. Sessions now learn only that a proposal was accepted.
- **A final hold recast.** After the gate held a bill for its date, the session proposed it again with a weaker exception that replaced the hold. Holds from final checks now stay for the reading.
- **Schema errors echoed the voucher.** A line missing one field failed the voucher's nullable schema, and the answer repeated the whole voucher. Two sessions resent it unchanged and ended with no proposal. The answer now names the missing field.
- **Correction reasons.** A bill meeting another version in Tally now says what differs: date, total, ledgers or line amounts.
- **Rechecks kept their first start time,** inflating session timings. A new attempt now starts its own clock.
- **The HTTP smoke test** announced a long-retired companion and plan, so the server refused its Tally check. It now sends this build's version and plan, which the companion runtime declares once.

## Memory and practice, rehearsed live (21 October 2026)

The same local stack ran slice 6 against the rehearsal companies:

- **A practice answer.** Sachin Infra's open question, how bank payments are booked, was answered through Attention's decision endpoint. The card closed, and its answer became the company's confirmed practice.
- **A rule.** An admin wrote one through the memory API: plant spares from one supplier go to plant repairs. Every session read it. The first bill from that supplier cited it, and the proposal kept the rule's text.
- **Bookings learnt.** Four new bills were approved and saved, all verified. Each taught its supplier's booking: the voucher type and the expense ledgers, not the taxes or round-off the bill printed.
- **An edit made in Tally.** One saved purchase was rebooked in Tally to another expense ledger. The next sync took 3 s, revalidated memory and demoted that booking. Read again, the bill followed the corrected books, without review. Approving it found Tally already holding exactly that voucher, a verified duplicate, and memory then held the corrected booking beside the demoted one.
- **Routings learnt.** The two-bank statements were approved again. All 11 rows reconciled with the vouchers already in Tally, nothing was added, and 7 payee routings were learnt.

**Usage.** Five runs (four bill, one statement) used 7 sessions: 749,000 input tokens (80% cached) and 19,900 output tokens.

**Found and fixed along the way:**

- **Rules missed by subject.** A session searched rules by its company's name, which no rule mentions, and missed the rule its supplier followed. `rules` now returns every active rule, bounded at 30 per client and employee.
- **A booking that changed value.** A supplier's second bill printed a round-off, so the booking learnt from its first changed value. Bookings are now the treatment alone, one entry for each way a supplier is booked.
- **Payees named two ways.** Some payees were named with the statement's code prefix and some without. A lookup now also matches a routing whose name contains the asked name, or is contained in it.

## Bill-wise settlement, rehearsed live (21 October 2026)

Slice 7 ran on Third Tally Company, whose synthetic QA18 books gained one supplier that keeps bill-by-bill balances. It was imported through Tally's XML interface with:

- an opening bill of 5,000.00;
- two purchases with New Refs, QA18/BW/101 for 11,800.00 and QA18/BW/102 for 5,900.00;
- a 6,000.00 part payment against QA18/BW/101.

The Educational dates are the 1st, 2nd or 31st.

- **The mirror balanced the bills as Tally does.** The sync's master and voucher collections already carry a ledger's opening bills and each line's references. `mirror.open_bills` reported 5,000.00, 5,800.00 and 5,900.00 open, matching Tally.
- **A statement settled them.** Four payment rows went through one session:
  - the row naming QA18/BW/102 settled it in full;
  - an unnamed 5,800.00, the only bill of that amount, settled QA18/BW/101;
  - a payment to a supplier that keeps no bills carried none;
  - an unnamed 2,000.00 the session put on account held for one click, because the opening bill was still open. Choosing "2,000.00 of QA18/OB/001" approved it.
  All four saved and verified in 9 s. Tally's own export shows each Agst Ref, and the next sync left only 3,000.00 of the opening bill open.
- **Bill to payment, both by Minkops.** A synthetic invoice, QA18/BW/103 for 11,800.00, was proposed in 48 s and saved with a New Ref under its invoice number; the readback carried it. A July statement row naming it was proposed as an Agst Ref and saved, and the next sync showed the bill settled.

**Usage.** Three runs used 3 sessions: 250,007 input tokens (80% cached) and 5,769 output tokens.

**Found and fixed along the way:**

- **A changed practice broke its sync.** Adding the first bill-by-bill supplier changed the company's bill-wise practice. The sync's probe then sent a NULL actor that PostgreSQL typed as text, so the publish failed and the PC retried it every tick. The actor is now typed, and a test changes a settled fact.
- **A failed tool call kept part of its work.** A propose call that failed partway had already saved its first rows. A failing call now rolls back to a savepoint, so only its log remains. That also keeps a database error inside a handler from aborting the session's transaction.
- **Sums came back as decimals.** PostgreSQL sums bigint amounts as numeric, which broke serialising a session's choices. Both bill sums are now cast back to bigint.
- **Company GUIDs mistyped.** Sessions mistyped the 36-character company GUID about once per tool and recovered when told. That is one wasted round trip per tool, carried to slice 12.

## Item-wise purchases, rehearsed live (22 October 2026)

Slice 8 ran on Third Tally Company's synthetic QA18 books, whose stock items have simple units and no batches.

- **Tally's own shape first.** A probe purchase was imported through XML with three items, one of them split between two godowns. Tally books each purchase ledger once among the voucher's ledger entries, with its items as inventory allocations. Each item reports its quantity, rate, amount, godown batches and one accounting allocation. The probe voucher was then deleted.
- **A bill booked item-wise.** A synthetic invoice from QA18 Inventory Depot listed two spares and cement, shipped to two named stores. One session looked up the stock items and godowns. It proposed each item with its quantity, rate, godown and purchase ledger, and its taxes as lines.
- **Waiting on a new probe.** The bill then waited on whether purchase orders track goods. That probe is new in this slice, and the company's unchanged books had never met it, so no card existed to release the bill. Fixed below. The next sync settled the practice from the books and released the bill.
- **Saved and verified.** The bill went to review because cement was a new ledger for that supplier. Approved, it was saved and verified in 3 s. Tally's own export shows the invoice view, each item in its godown, and each purchase ledger once.

**Usage.** One session: 91,171 input tokens (76% cached) and 3,581 output tokens.

**Found and fixed along the way:**

- **A probe the books never met.** Probes ran only on newly published versions, so a probe added in a release never ran on a company whose books did not change. A bill could wait on its question with no card to answer. Each version now records the probes run on it, and a sync that publishes nothing runs any missing probe on the latest version.
- **A settled practice released nothing.** A practice the books settled after a bill began waiting on it left the bill waiting. Settling one now checks those bills again, as an answer does.

## Signed e-invoice QR codes (22 October 2026)

Slice 9 began as a feasibility check, and each question came out in favour:

- **Decoding.** `zxing-cpp` (a 1 MB wheel) decodes QR codes from rendered pages; a dense e-invoice code needs about 300 DPI. On the client's own sample bills it found one QR code, a 75-character payment code rather than an e-invoice. Reading a file costs 0.1–0.35 s, of which decoding is 10–20 ms. None of the PR Infra UAT bills carries a QR code.
- **Verification.** An e-invoice QR code is a JWS (RS256) whose `kid` is the SHA-1 thumbprint of the IRP's signing certificate, and whose payload holds the registered invoice. NIC publishes its production keys per IRN generation period (six for IRP 1 since August 2020, three for IRP 2 since April 2023), and IRIS publishes two for IRP 6. NIC's own published sample signed code verifies against the key NIC lists for August 2020, and fails once its contents change.
- **Coverage.** Clear's certificate link (IRP 4) refuses downloads. IRPs 3 and 5 list their keys only in the browser. Their codes read as unverified: still the invoice's own data, but no proof of registration. The trust store holds production keys only; a sandbox-signed code proves nothing.

No live run used a real e-invoice: no available bill carries one. The tests cover NIC's real sample code and synthetic codes signed by a test key. A real e-invoice from a PR Infra supplier is on the manual testing list.

## Review surface, rehearsed live (22 October 2026)

Slice 10 ran the console against the dev stack, the companion and Third Tally Company's synthetic QA18 books.

- **A run reviewed.** An earlier rehearsal run of 15 bills read as 5 needing a decision, 8 saved and 2 already in Tally. Each held bill showed its hold, its own reason and only the decisions its hold allows, such as Retry save or Recheck. Details showed each proposal's lines, items with their godowns, and the evidence it quoted. Attention grouped its items by client.
- **A run started, approved and saved in the console.** A synthetic item-wise invoice from QA18 Inventory Depot was uploaded on the workflow's page and routed by its addressee. It was read, proposed and approved with one click, then saved and verified in Tally 2 s later.

**Usage.** One session: 106,273 input tokens (80% cached) and 2,612 output tokens.

**Found and fixed along the way:**

- **The launch was refused.** The mock tenant's saved settings locked bill entry to a company without naming one. "The company each bill is addressed to" sent no company mode, so that default won and the server refused the run. The form now always sends the mode it shows, and starts on a tenant's locked company when it belongs to the client.
- **A title pushed the status off a phone's screen.** A run's title listed every file, cut at 200 characters, and one long name pushed the task's status out of view. A title now names the first file and counts the rest, and a long one wraps.
- **One run, three wordings.** The task's summary said "need attention" where the review says "need a decision", with no singular, and kept its launch wording until the first session ended. One summary now counts as the review does, in each workflow's words, from launch on, and moves on as soon as a lane starts reading.
- **Amounts without grouping.** Holds, refusals and settlement choices printed 188800.00 beside a console showing 1,88,800.00. One formatter now words every amount meant for people.
- **A worker on mixed code.** A worker started before an edit loaded the new bill handler beside the old run module, and its lane failed. The lane left the item for a successor, which resumed it after the restart. Only a checkout edited under a running worker mixes code like this.

**Found, carried to slice 12:** the session read the supplier's confirmed booking (QA18 Plant Repairs, by name) and proposed a ledger GUID it was never given, which named QA18 Equipment Hire. Tally numbers a company's masters in sequence, so a guessed GUID can name another real master. The booking differed from the confirmed one, so it went to review as designed. The rehearsal approved it to exercise the button, so Third Tally Company holds QA18/INV/STK/002 with its spares under QA18 Equipment Hire; the booking memory learnt from it is disabled.

## Performance, benchmarked live (22 October 2026)

Slice 12 ran both targets on the local stack: the API, a worker with 12 lanes, the headless companion, TallyPrime
in Educational mode and `gpt-6-luna`.

- **Bills: 50 read in 5 min 30 s** (target 10 min). Fifty labelled synthetic bills, ten from each rehearsal
  company's package, ran as one run routed by addressee. The PC's refresh took about 5 s. Sessions took 68 s at
  the median and 112 s at most. The fixture scorer graded 44 of 50 as labelled. The five conflicting versions were
  proposed, as they are until a save meets the other version in Tally and holds. One bill followed the booking
  Tally now holds for that very bill, re-booked by slice 6's demotion rehearsal, rather than its original label.
- **Statements: 1,232 rows in 4 min 31 s** (target 15 min). The synthetic month
  (`icici-detailed-statement-sep-2026.xlsx`) ran as 13 chunks of up to 100 rows, the 13th waiting for a free lane.
  Chunk sessions took 129 s at the median and 162 s at most. Its 881 payees are made up and no rehearsal company
  holds them, so 1,227 rows held as `ledger_unresolved` after their lookups: the run measures the pipeline, not
  routing. For it, Third Tally Company gained one bank ledger with the statement's account number,
  QA18 ICICI Synthetic Current.
- **Where the time goes.** The 529 lookups and proposals of the bill run averaged 3 ms and took 14 ms at most, so
  neither the database nor the four-connection pool is the limit: the model is.

**Usage.**

- Bills: 50 sessions, 5,336,041 input tokens (79% cached) and 104,934 output; about 107,000 input and 2,100
  output per bill.
- Statements: 13 sessions, 3,602,452 input tokens (86% cached) and 150,328 output.

**Found and fixed along the way:**

- **Round trips the contract caused.** A bill printing no tax was refused for its zero tax (five times), an empty
  GSTIN check was refused (three times), and statement chunks looking up their payees were refused above 20
  subjects (18 times). Each cost a model round trip; all three now answer.
- **References in reviewers' text.** Held rows read "no matching ledger was found in C5". Reasons a person reads
  now name the company or master each reference stands for.

## Cut-over and the final build, checked live (22 October 2026)

Slice 13 rehearsed the cut-over's new step, then ran the final build end to end on the restarted local stack:
the API, a worker with 12 lanes, the console, companion 0.11.0, TallyPrime in Educational mode and `gpt-6-luna`.

- **A client's workspace created.** A scratch database migrated from empty through 0032. There,
  `install_workflows pr-infra --create-tenant "PR Infra"` created PR Infra for its verified administrator, with
  its client business, both workflows bound to the Accounts desk, and the agreed rule. A dry run left nothing
  behind, and a repeat changed nothing. Another administrator and an unverified owner were refused.
- **A bill, from the console.** A new item-wise invoice from QA18 Inventory Depot (QA18/INV/STK/003) was read in
  about 60 s and approved with one click. It was saved and verified in Tally 3 s later, its spares booked as
  three of that supplier's four earlier purchases were.
- **A statement, from the console.** A three-row October statement for the synthetic ICICI account continued
  September's closing balance and was read in one session. Save ready entries saved and verified its receipt and
  a payment.

**Usage.** Three sessions: 252,859 input tokens (79% cached) and 6,786 output.

**Found and fixed along the way:**

- **The runtime could not have reached its database.** The deployment mounted the new instance, while
  `configure_runtime.py` still wrote the shared instance's socket into secrets that already exist and are never
  rewritten. The runtime's secrets are now named for the new instance, beside the parked build's.
- **A rollback could have lost its images.** Retention kept only the three newest; images tagged `parked-…` are
  now kept. A rollback also reinstalls the parked companion, which the rebuilt one cannot stand in for.
- **A refusal printed a traceback.** The install command now prints the reason and exits 1.
- **A supplier payment held as inventory.** The statement's payment to QA18 Inventory Depot cited
  QA18-INV-STK-003. The skill listed inventory among what an entry cannot carry, so the session held the row as
  Manual entry needed. Statement entry 1.1.1 says a row records money moving, never what it bought. Rerun, the
  payment was proposed to the supplier's ledger and saved, and the first run's two saved rows were found in
  Tally, never written twice.
