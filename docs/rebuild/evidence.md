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
- **What the adapter does today.** `platform/src/minkops_platform/runtime/openai_hosted.py` calls `sessions.create(agent, environment, input, stream=True)`, passes no tools, and re-attaches to a dropped stream up to three times.

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
