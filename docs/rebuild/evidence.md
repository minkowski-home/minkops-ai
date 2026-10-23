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

### Constrained final answers, measured live (22 October 2026)

A bill run of 12 synthetic bills had 78 of 89 `propose` calls refused for their
shape: the model wrote fields the instructions described (`{page, quote}` evidence, a
cost centre with its category) rather than the schema's, and five sessions gave up.
Probed with `gpt-6-luna` through SDK 3.19.0:

- **Function tools are not constrained.** Asked to, the model sent arguments that
  break the tool's schema, and the provider passed them on.
- **`strict` is refused.** `agent.tools[0].strict` returns 400 `unknown_parameter`;
  `agent_tool_param.py` declares only name, description, parameters and
  `defer_loading`.
- **A final answer is constrained.** `agent.text.format: {type: json_schema, schema}`
  holds the turn's last message to the schema: asked for the same malformed value,
  the model answered within it. The message is listed with `phase: final_answer`.
- **Lookups and corrections fit around it.** A turn calls its function tools, then
  answers within the schema. An `agent.session.input.message` (its `input` a list of
  user messages) starts the next turn, whose answer is constrained again.
- **The bill proposal's schema is accepted whole.** 9,158 characters using `type`,
  `properties`, `required`, `additionalProperties`, `items`, `anyOf`, `enum`,
  `description`, `pattern`, `minLength`, `maxLength`, `minimum`, `maximum`,
  `exclusiveMinimum`, `minItems` and `maxItems` (`tools.CONSTRAINED`).
- **Usage is per turn.** A session's own `usage` stayed null; each turn reports its
  own, so a session's usage is every turn's, summed.

### Constrained answers, checked live (22 October 2026)

Five synthetic bills that had returned no proposal before (B03, B04, B07, B09 and
B11 of the 22 October test pack) ran through Bill entry 1.5.0 at high effort on the
fast tier. No answer was refused for its shape (none of 9, against 78 of 89 before),
and every bill reached a proposal. Each document fact the pack determines was read
exactly where printed. All five held for a reason a person can act on: a
withholding with no precedent, a new supplier, a cost centre named on a company
that keeps none, a split of one expense across two cost centres (one ledger line
carries one cost centre today), and a credit note booked on repeated ledgers, whose
refusal now says to combine them. Bills took 94 to 165 seconds.

The HDFC sheet that held as "Layout unknown" was proved on the first answer in 17
seconds: its SUM totals, saved with float error, read as their paise amounts, and its
closing balance printed twice agreed at both copies. Its 920 rows ran as 19 chunks of 50,
each answered once, in about 100 seconds. Of the 597 rows the pack's key expects to
resolve, 594 were proposed; of the 323 it expects to need a person, 245 held, mostly as
`ledger_unresolved` for payees no ledger is, and the rest were proposed, which standing
approval leaves for a person until a payee is booked twice. Every proposed row used the
family the key expects. Eight counter ledgers differ from the key: seven follow the
party the narration names, and one splits a batch payment between the two suppliers it
names; the key's amounts and references are from another generation of the pack.

One chunk hung after its first correction: the turn the correction started began after
the stream had ended, and a stream opened on the idle session never delivered it. The
driver now waits until the session shows the corrected turn before following it; restarted
with that change, a successor resumed the hung session and checked its second answer.

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
- **A finished run still said Saving.** "3 entries approved. Saving in Tally." stayed under the completed run. A
  notice that something is saving now goes once the run shows nothing approved or saving.

## GST returns, rehearsed live (22 October 2026)

Whether Tally's GST returns count what Minkops enters was checked in Pradeepraj Infra, the rehearsal company with
GST switched on. TallyPrime stores its own verdict for its returns on each voucher (`VCHGSTSTATUSISINCLUDED`,
`…ISUNCERTAIN`), so throwaway purchases dated 31 October were imported, read for it, and deleted.

- **What Minkops wrote was left out.** All 8 purchases Minkops had saved there were Uncertain. So was every other
  purchase in the company: their suppliers and ledgers are synthetic, without GST registrations.
- **Tally does not fill the supplier's details.** An imported purchase from a registered supplier kept only its
  registration type. Sent, the GSTIN, state, country and place of supply were all kept. Without them, the purchase
  stayed Uncertain.
- **Nor does it take rates from the masters.** With the supplier's details, a purchase stayed Uncertain until its
  taxed line stated its taxability, type of supply and each duty head's rate under "Specify in Voucher". Then it
  was included. "Specify Details Here" and "Use GST Classification" stayed Uncertain. So did a line on a ledger
  configured at 18%, until the voucher stated the rate.
- **Tally checks neither the tax head nor the rate.** A Delhi supplier's purchase charging CGST and SGST was included,
  and so was a line stating 12% while its tax lines charged 9%. The bill gate checks both first.
- **Inter-state.** A Delhi supplier's purchase charging IGST at 18% was included.
- **Item-wise purchases stayed Uncertain.** The stock item carries no GST details, and neither stated rates nor an
  HSN on the item entry or its ledger allocation changed that. Minkops states the supplier's details for such a
  bill, and a saved one Tally leaves out keeps a note saying so.
- **A bill, end to end.** For the rehearsal, Pradeepraj Infra gained a synthetic registered supplier, MKQA GST
  Supplies (Andhra Pradesh, Regular). Its synthetic invoice MKQA/GST/001 (1 October 2026, CGST and SGST at 9% on
  10,000.00) was read with its buyer GSTIN, place of supply and type of supply, approved in the console and
  saved. Tally kept the supplier's details and includes the purchase in its returns; Minkops read both back and
  recorded the verdict.

**Usage.** Two sessions: 445,386 input tokens (88% cached) and 17,280 output.

**Found and fixed along the way:**

- **A session gave up on a refusal it could not read.** Its tax lines lacked several required keys, and the
  refusal named the whole voucher, cut off: `best_match` stops at a nullable value whose schema reports more
  than one error. Refusals now name each fault where it is, and the new GST fields are optional, asked for only
  where a company needs them.

## Replacing a PC, rehearsed live (22 October 2026)

The move was rehearsed against TallyPrime in Educational mode, with the five rehearsal companies open, on a scratch
database migrated through 0034 and its own API. Two headless companions (`scripts/companion_dev.mjs`, companion
0.11.0) stood in for the two PCs. Each kept its own state, and they read the same Tally through the WSL relay, one
after the other.

- **The old PC.** OLD-PC found the five companies, and an admin authorised them for "Rehearsal companies". Its first
  sync mirrored them in full in 10 s: 7 to 23 vouchers and 119 to 134 masters each. The probes raised 21 practice
  questions.
- **The replacement.** OLD-PC was disconnected, and NEW-PC registered and refreshed. Each of its five "New company
  found" cards offered to continue the client's company from OLD-PC.
- **Continued.** One decision per card returned the client's existing company, now on NEW-PC, and the duplicates
  were removed. The sync the decisions queued rebuilt all five in full in 10 s, with reason `pc_changed`. Each
  rebuild matched the old copy's voucher and master counts exactly. The copies were identical, so no voucher row
  was rewritten and no "Older copy of the books" card was raised. The 21 practice questions stayed with their
  companies, and none was raised again.

Restoring an older backup on the new PC, and a bill saved through Minkops Dev after the move, need a person at
Windows. Both are on the manual testing list.

## Demo readiness, regression-checked live (23 October 2026)

Workstream 10 of the [plan](demo-readiness.md) ran on the local stack: the API, a worker with 12 lanes, the console,
Minkops Dev 0.11.5 on Windows, TallyPrime in Educational mode and `gpt-6-luna` at medium effort. Runs used
`all_outputs` unless noted, and were scored as the plan's appendix says, the answer keys read only after each run.

These are regression checks. They show the pipeline works end to end, holds what it should and writes only what it
may, on books built for the pack. They do not show accuracy on a client's books:

- The pack's key was aligned with the rehearsal companies' supplier history, so a bill booked to the key's ledger
  mostly shows that Minkops follows clean, consistent history.
- The same pack ran on the same companies all session. Memory and Tally hold its earlier saves and choices, which
  feed later runs: B02's chosen head drove B32, B36, B40 and B44, and earlier saves count as precedent for standing
  approval.
- One Tally release ran, TallyPrime Edit Log 1.1.7.2 in Educational mode, which saves only vouchers dated the 1st,
  2nd or 31st; the pack's bills are dated for it. Ledger creation and its read-back ran only in the dated shape
  that release writes.
- The only real document was one client statement, whose payees the books lack: it shows safety, not accuracy. No
  client's bills ran.
- The 50-file run cap predates the plan, and the pack was sized to it.

Accuracy stays unproven until PR Infra's own bills and statements run against books that hold their payees. Until
then its workflows review everything ([cut-over](cutover.md#5-fresh-workspaces)).

- **Bills: 50 in 7 min 17 s** (target 10 min), upload included, in two batches (Bill entry 1.9.0). Every printed
  date, total, company and number matched the key, except B17, a proforma held as not a bill as the key wants.
  The 15 added bills B31–B45 were proposed to the key's ledgers, and the five expected holds held: B46 as a copy
  of B31 (naming it), B47's overstated total, B48's unregistered new supplier (offering Create this ledger), B49's
  buyer GSTIN and B50's date before the books begin. B02, B03, B09 and B11, entered earlier, were found in Tally.
- **Unattended exposure.** 15 bill proposals had no review note and at least two precedents; each was on the
  key's ledger. One, B22, an annual maintenance contract running past 31 March, followed its supplier's four
  earlier bookings, as the books say; the key would leave it to a person.
- **Statements: S01 and S02 in one run**, 2,180 rows in 20 min 51 s, sharing the lanes with two other runs
  (Statement entry 1.6.0). No date or amount differed from the key, no answer landed on another row, no transfer
  held, and the nine R K Supplies rows held, none booked to another creditor (the earlier run booked five to MKQA
  GST Supplies). Of the 1,417 rows the key resolves, 1,408 were booked to its ledger, 8 held and 1 booked to
  another supplier (below). Of the 763 rows the key sends to review, 600 held. The other 163 were booked: 81 bank
  charges split into the fee and the tax their narrations itemise, 73 payments to the supplier a short narration
  names, and 9 single cases, among them a part payment, a refund and a returned transfer, each booked to the
  party it names or reverses. Under standing approval 183 rows would be written unattended: 182 on the key's
  ledger, and one intercompany advance booked as five earlier ones were, which the key leaves to a person.
- **A client's real statement** (1,232 rows, kept outside git): 16 min 27 s with the lanes shared. 1,217 held as
  other side unclear, because the synthetic books lack its payees; 12 were proposed and 3 found already in Tally,
  each naming the ledger booked in its narration; no transfer held (the earlier run held two for a same-account
  pairing).
- **Protocol 7 in Tally.** B11 (a 60/40 split on a ledger keeping cost centres) and B03 (one head at three GST
  rates), saved earlier, read back from Tally exactly as approved through a fresh read-only export, as did every
  save below.
- **Learning loops.**
  - Recheck: B09, held after its supplier was created, was rechecked. The PC refreshed, the run pinned the new copy
    and cleared its request, and the bill was read again against it.
  - Choose and approve: B02's supplier had been booked away from its history in all four earlier runs. A person
    chose its historical head and B02 was saved. The next run proposed the same supplier's B32, B36, B40 and B44
    to that head unprompted, with two precedents each.
  - Create this ledger: B09's supplier was created bill by bill with a 30-day credit period under Sundry
    Creditors, and read back. R K Supplies, a payee new to Pradeepraj Infra, was created from its 1 October row
    under the group chosen, and the payment entered with it. The run's eight other R K Supplies rows were
    proposed to it as chosen.
  - Learning from Tally: bills saved earlier were found in Tally when proposed again, and held copies in older runs
    were reconciled after the next sync.
- **Standing approval.** B01–B30 rerun under `only_exceptions` (Bill entry 1.10.0): seven bills with two to six
  precedents and no note were written unattended (B06, B18, B19, B24, B25, B27, B30). Each read back from Tally as
  approved, on the key's ledger. B25, a supplier's debit note for a price increase, was entered as a Purchase,
  which raises what is owed; a note for such bills is still [not in this plan](demo-readiness.md#not-in-this-plan).
  B20's adjusted advance, B08's copy and three new bookings waited for a person, as did B22 under a service-period
  note since reverted (below).

**Usage.**

- Bills, 50: 50 sessions, 4,829,138 input tokens (75% cached) and 233,441 output.
- S01 and S02: 45 sessions, 8,102,493 input tokens (81% cached) and 608,079 output.
- The client's statement: 25 sessions, 2,997,331 input tokens (79% cached) and 235,809 output.
- Bills, standing approval: 30 sessions, 2,670,598 input tokens (73% cached) and 118,740 output.

**Found and fixed along the way:**

- **A new supplier's bill without its bill reference.** B09's supplier was created bill by bill, but the server
  kept only the created ledger's identity, so the plan carried no New Ref. Tally took the voucher and kept it on
  account, and the companion, finding a voucher other than the approved one, held the save as uncertain; nothing
  was imported twice. The whole master is now kept as Tally holds it (`79e5f07`).
- **"Booked as proposed" when it was not.** Found in Tally later, B09 was called booked as proposed though Tally
  kept it on account. A bill Tally books as proposed is still a duplicate, but its note now names the bill
  reference or cost allocation Tally keeps instead (`22058a4`, `8533deb`).
- **Minkops's own saves taught twice.** Held copies, in older runs, of bills saved from other runs were noted
  "Entered in Tally by hand" and taught their bookings again, inflating the precedent standing approval counts.
  They are now noted as Minkops's own saves, and no voucher teaches twice (`8647256`, migration 0039).
- **A payee the row never printed.** In S01, a payment naming QA18 Cement Depot was booked to QA18 Coastal
  Equipment Hire, its answer naming that supplier as payee. An answer naming a payee its row does not print is
  now refused, as one restating another row's amount is (`efd24e0`). Measured on stored answers from runs made
  before it, the check would refuse none of the 1,184 payees named on the client's real statement, and 2 of 2,882
  on the synthetic ones. One of those was a returned transfer that names no one, so the refusal says the payee
  may be left empty (`11fb38c`).
- **A tax group offered for a payee.** The form for a payee's new ledger listed Duties & Taxes, a sub-group of
  Current Liabilities. Tax groups are no longer offered (`db4a987`).
- **A test that depended on others.** The migration test for ledger jobs validated an old constraint against jobs
  other tests had left in the shared database (`018d4de`).
- **Reverted after review: a note for service past the year end.** B22 was proposed with no note in one run of
  five, so a note was added for any bill whose service ran past 31 March (`6d4b0ec`, Bill entry 1.10.0). It came
  from one bill whose booking the books supported. It turned the key's view into fixed policy that nothing
  cleared, and assumed the company's year end rather than reading it. It was reverted (`da62cd1`, Bill entry
  1.11.0). A client who wants such bills reviewed says so in a rule.
- **On the local stack only:** the standing-approval run waited 23 minutes after code changed under a running
  worker, which then imported a new module against an old one. Each lane left its items for a successor, as it
  must during a deployment, and a restart resumed the run. A deployed image never changes under its worker.

## Cut-over (23 October 2026)

The rebuild went live by the [runbook](cutover.md), from `main`.

- **Before.** Production ran the old build: `minkops-solution-api` and `minkops-operations` on
  `solution:workflow-recovery-20261021-a944022`, against a `minkops` database on Myndral's shared instance.
- **Database.** `minkops-books`, PostgreSQL 16 at Myndral's tier (`db-f1-micro`, zonal, 10 GB), migrated through
  0041 by `provision_database.py`. `verify_database_restore.py` restored it logically (52 tables, 41 migrations) and
  removed the bootstrap login. `configure_runtime.py` wrote the `minkops-books` connection secrets and kept the
  model key.
- **Cost.** The instance bills to `minkops-ai-prod`. At the catalog rates `infra/README.md` records, a 31-day month
  costs about CAD 13.48 before backups and network, where the envelope reserved CAD 8 for Minkops' half of the shared
  instance. The same day the owner revised the envelope to CAD 27 (about CAD 15 for the instance with backups,
  CAD 10 for Minkops-exclusive resources, CAD 2 of contingency), and the project alert, which counts the instance,
  to CAD 25.
- **Runtime.** `solution:rebuild-20261023-db786c7` (digest `sha256:8f38285f…`), built from `main` at `db786c7` with
  `infra/solution.Dockerfile` and checked with `install_workflows mock-client --validate-only`. It serves the API,
  the 12-lane worker job and the recovery service on `minkops-books`, each Ready with all traffic. The interest API
  kept its unchanged image. Public sign-up answers 404.
- **Console and site.** `app.minkops.com` serves the new console. `minkops.com` offers companion 0.11.5, an unsigned
  release candidate (`Minkops-Setup-0.11.5.exe`, 102,599,914 bytes), with its checksum, update feed and release notes.
- **Workspaces.** Only the mock client's ("Mock client", with its "Rehearsal companies" client business), with the
  owner invited as its first admin. PR Infra waits for the owner's decision.
- **The old build, retired.**
  - Its database was dumped once with PostgreSQL 16's `pg_dump` into an owner-only folder outside git. Restored into
    a throwaway database, the dump matched the source: 37 tables, 1 view and 7,721 rows, table by table.
  - Then its database and its three roles left Myndral's instance, and its two database secrets were deleted.
  - Minkops' service accounts lost their Cloud SQL access in Myndral's project. They keep their per-secret access to
    Myndral's SMTP secrets, which the new build sends mail with.
  - Its Cloud Run revisions and solution images were deleted, and the earlier Hosting versions too, the 0.9.1
    installer's among them.
  - Myndral's instance, databases, users and secrets are untouched.
- **This PC.** Minkops 0.11.5 is installed over 0.9.1 and running; Minkops Dev is uninstalled.

**Found on the way:**

- **The candidate would not package** (fixed in `378df93`). electron-builder merges a repeated publish list into
  the list's first entry. The packaging script passed `package.json`'s `build` again, so the candidate's update feed
  was refused. Dev builds turn publishing off, which is why they passed.
- **Operator snags, worked around.** Each is worth fixing in the tools:
  - `provision_database.py` expects its proxy on 127.0.0.1:5433, which the local dev database also uses, so the
    local stack was paused meanwhile.
  - `verify_database_restore.py` looks for PostgreSQL 16 at `/usr/lib/postgresql/16/bin`, so it was run with the
    local copy's tools.
  - Cloud Build's default service account here cannot read its source bucket, so the image was built and pushed
    with local Docker.

