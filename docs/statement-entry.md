# Statement entry

Version 0.2 uses the same managed hosted agent runtime as Bill Entry, with its
procedure in the Statement Entry skill. Windows companion 0.8.0 / plan protocol
4 applies and independently verifies approved Payment/Receipt plans.

Select CSV/XLSX statements and the latest confirmed complete Source Discovery on
the destination PC. Optionally select a separate CSV/XLSX branch mapping. Both
mock-client and PR Infra use this shared workflow. There are no fixed bank or
Other-side ledger settings, client-specific ledger names or branch-routing rules.

## Input and routing

Branch is a client business label, **not a bank branch**, and has no predefined
relationship to a company, ledger, group or cost centre. The agent receives all
canonical transaction rows as JSON, the original source files, the complete
indexed discovery evidence (masters, period vouchers and confirmed notes), and
the optional mapping file. It interprets narration, references, account headers,
branch conventions and relevant independent accounting history to select the
company, bank, counter ledger, voucher type and any supported cost allocation.
Mapping layouts are interpreted by the skill; they do not introduce Python
matching rules. An unfamiliar branch label or absent mapping alone cannot
invalidate an otherwise evidenced classification. Genuinely ambiguous company,
bank, ledger or client conventions hold the affected row with a plain reason.

The application binds selected GUIDs to the pinned company's discovered records;
it never picks an accounting destination. It independently validates the bank's
Bank Accounts ancestry, books beginning date, distinct ledgers, active
Payment/Receipt type and supported cost-centre/category relationships. It retains
every source row, holds missing interpretations, rejects foreign or repeated row
references, and cannot accept model-supplied replacement financial values.

One hosted session interprets the selected statements together so it can reuse
evidence across rows. Indexed discovery files retain full records; they are not
dumped into every transaction's prompt or sampled. Hosted input limits are 45
files and 8 MB including discovery and transaction JSON; reduce the statement
scope or voucher period when exceeded. Discovery itself still collects only
unlocked companies already open in the running Tally instance, identified by
GUID regardless of installation location or data directories/drives.

CSV accepts UTF-8 BOM and Windows-1252, including comma, semicolon or tab delimiters. XLSX uses native dates or explicit DMY/MDY/ISO text ordering and holds uncached formulas. Header synonyms identify Date, Branch, Balance, optional Reference/Narration, and either signed Amount or separate Debit/Credit columns. Unknown/duplicate columns hold the file for correction in the original tool. Legacy XLS requires conversion in Excel. Limits are 10,000 rows, 100 columns and the existing bounded upload/workbook sizes.

An opening-balance row or explicit opening balance establishes the chain. Each row must satisfy previous balance + signed transaction = printed balance. Missing or unverifiable balances hold affected rows; dates and amounts are never guessed. Existing source bytes and hashes remain pinned for the run. Recheck a corrected source by refreshing and starting a new run.

## Preview, writes and recovery

The preview shows per-branch counts, payments, receipts, dates and check results,
plus each proposed bank/counter ledger and its interpretation evidence. Exceptions
come first, saved/duplicate rows collapse, and large lists paginate. Write ready
rows approves immutable plans. Only exceptions mode provides standing
authorization for eligible rows. One file summary appears in Attention; details
stay in the task and shared spreadsheet-safe CSV export. Export waits until
processing/saves settle. Saved setup and dashboard quick runs retain statements
and the optional mapping across refreshed file IDs; a missing saved mapping
requires an explicit new selection rather than silently omitting it.

Identity combines bank reference, date, signed amount/direction, running balance and occurrence number; destination identity also includes tenant, company GUID and bank ledger. Overlaps therefore reconcile without dropping two real identical transactions. Native tags use stable UUID5 identities in narration. Any other voucher on the same date with the same bank amount holds as a possible existing entry, including one tagged by Minkops for a different identity, unless it is a sibling row of the same run (proven distinct by the run's balance chain). Protocol-5 companions receive every approved row as a v5 voucher; a row without pinned identities is refused rather than written by the retired statement writer. Conflicting overlap routing holds every affected proposal before dispatch.

Every approved voucher intent is persisted before the first import. The companion serializes work and writes an encrypted, fsynced local attempt fence before importing one voucher. It rechecks company/master identities, reads first and verifies date, type, both ledger amounts, tag and any cost allocations afterward. A timeout permits reads only; a subsequent retry cannot resend that uncertain intent. Retry save checks reconcile technical holds; possible existing or unresolved imports may require manual handling in Tally. Pause prevents new dispatch; Stop preserves verified facts and cancels remaining plans. Late receipts remain truthful without resuming stopped work.

Native date collections use calendar components because Tally can coerce typed
date variables or numeric date conversions differently. Returned dates are
independently checked. Contra, split postings, unsupported statutory/billwise
allocations, master creation, undo and silent source correction remain outside
the write contract; the skill must hold them rather than flatten their accounting.

Apply migration `0010_statement_ai_settings.sql` before reinstalling workflows.
It retires only the old Statement Entry ledger/strategy settings and preserves
review/date/balance preferences, other workflows and historical run snapshots.
Previously approved manifests can still reconcile. Unexecuted legacy statement
runs without a pinned agent bundle require an explicit new run; the retired
classifier is not retained as a fallback.
