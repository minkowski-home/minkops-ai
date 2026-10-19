# Statement entry

Version 0.1 uses deterministic Python parsing and Windows companion 0.8.0 / plan protocol 4. Bank rows never reach a hosted model; the handler cannot declare a hosted execution bundle. Source Discovery may separately use its existing optional analysis.

Select immutable CSV or XLSX snapshots, a confirmed complete Tally discovery on the destination PC, a bank ledger for each enabled company, and an **Other-side ledger**. The `single` counter strategy is the first registered strategy; later strategies can replace it without changing voucher construction. Both mock-client and PR Infra enable Source Discovery and Statement Entry. PR Infra's Other-side ledger remains unset until real discovery and operator configuration; no customer ledger names or statement schema are hard-coded.

## Input and routing

Add a manual Branch column. Normalize case and spaces and require exactly one discovered company, ledger, group, cost centre or cost category match. A company routes to its own books; a ledger becomes the counter ledger. A group needs one posting ledger beneath it. A cost centre requires an enabled Other-side ledger and its discovered category; a category needs exactly one centre. Ambiguities hold the row. Each destination validates the bank's Bank Accounts ancestry, books beginning date, distinct ledgers, and an active Payment or Receipt voucher type. Multiple types require an explicit choice.

CSV accepts UTF-8 BOM and Windows-1252, including comma, semicolon or tab delimiters. XLSX uses native dates or explicit DMY/MDY/ISO text ordering and holds uncached formulas. Header synonyms identify Date, Branch, Balance, optional Reference/Narration, and either signed Amount or separate Debit/Credit columns. Unknown/duplicate columns hold the file for correction in the original tool. Legacy XLS requires conversion in Excel. Limits are 10,000 rows, 100 columns and the existing bounded upload/workbook sizes.

An opening-balance row or explicit opening balance establishes the chain. Each row must satisfy previous balance + signed transaction = printed balance. Missing or unverifiable balances hold affected rows; dates and amounts are never guessed. Existing source bytes and hashes remain pinned for the run. Recheck a corrected source by refreshing and starting a new run.

## Preview, writes and recovery

The preview shows per-branch counts, payments, receipts, dates and check results. Exceptions come first, saved/duplicate rows collapse, and large lists paginate. Write ready rows approves immutable plans. Only exceptions mode provides standing authorization for eligible rows. One file summary appears in Attention; details stay in the task and shared spreadsheet-safe CSV export. Export waits until processing/saves settle.

Identity combines bank reference, date, signed amount/direction, running balance and occurrence number; destination identity also includes tenant, company GUID and bank ledger. Overlaps therefore reconcile without dropping two real identical transactions. Native tags use stable UUID5 identities in narration. Untagged existing date/amount/bank matches hold as possible existing entries. Conflicting overlap routing holds every affected proposal before dispatch.

Every approved voucher intent is persisted before the first import. The companion serializes work and writes an encrypted, fsynced local attempt fence before importing one voucher. It rechecks company/master identities, reads first and verifies date, type, both ledger amounts, tag and any cost allocations afterward. A timeout permits reads only; a subsequent retry cannot resend that uncertain intent. Retry save checks reconcile technical holds; possible existing or unresolved imports may require manual handling in Tally. Pause prevents new dispatch; Stop preserves verified facts and cancels remaining plans. Late receipts remain truthful without resuming stopped work.

Native date collections use calendar components because Tally can coerce typed date variables or numeric date conversions differently. Returned dates are independently checked. No automatic batch import, Contra, branch inference rules, reconciliation fields, master creation, undo or silent correction is included in this slice.
