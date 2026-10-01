Read all pages of all selected PDF and image bills, including scans.
Use provided PDF/image capabilities and installed pymupdf when helpful. Read the
confirmed catalog and references in context.json. Pick the appropriate confirmed
destination sheet for each bill using evidenced business meaning. Use its exact
named table (table:null for a plain sheet). Route using client context, actual
reference records and bill evidence rather than fixed file names or schemas.
If no destination is justified, omit its records and add {"source_file_id":"ID",
"reason":"why recognition needs clarification"} to unresolved. Never guess.
column names and types. Never invent or silently substitute source values.
Extract one record per bill, or multiple rows when the confirmed sheet models
line items. Keep numeric amounts as numbers; leave unavailable values null.
Leave entry_id values null; the application generates these from the run and record.
Write /workspace/outputs/result.json with EXACTLY:
{"records":[{"source_file_id":"supplied input ID","destination_file_id":"catalog file ID",
"sheet":"confirmed sheet","table":null,"operation":"append","data":{"actual header":"value"},
"evidence":[{"field":"actual header","page":1,"quote":"observed text"}],
"findings":["uncertainty or missing data"]}],"findings":["overall unresolved issues"],"unresolved":[]}.
Only use append by default; edits require explicit user selection. Include all
input files even if extraction fails; record missing evidence as findings.
Do not write the client workbook. The application validates and obtains approval,
then applies edits reliably. Do not claim PO/receipt reconciliation without records.
Reference matches must have evidence. Don't expose private unrelated files.