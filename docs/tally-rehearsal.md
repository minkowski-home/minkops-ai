# Five-company Tally rehearsal (18 October 2026)

Status: all five companies seeded and reconciled against full native exports.
Each has 59 planned masters and 50 vouchers; all 75 two-page bills are generated,
hashed and visually checked. First saves and duplicate replays passed through
the production adapter. This does not claim a hosted AI Bill Entry run.

The fixture scripts start from the open-company contract on `staging` commit
`1e2d18b34bda802316b9dde0c5ed43e004e7d992`. They never locate, open, close or
restart Tally, select data folders, or handle passwords. The operator must open
and unlock the companies first. A GUID pins each destination; the repeated
company numbers `100000` and `100001` are display values.

## Local package

`packages/tally-demo-20261018/` is ignored by Git because it contains local native
exports, import evidence and generated binaries. Its five company directories are:

- `01-pradeepraj-infra`
- `02-sachin-infra-2025-2026`
- `03-second-test-company`
- `04-test-company`
- `05-third-tally-company`

Each company has 15 individual two-page PDFs in `bills/`, a combined
`all-bills-preview.pdf` for inspection, and `evidence/expected-bills.json` with
file hashes, exact amounts, dates, native master GUIDs after seeding, and expected
outcomes. Select **only the bills folder** for Bill Entry. Keep previews,
baselines, plans and answers out of synchronized input folders.

Every invoice, supporting printed date, and seed voucher uses the 1st, 2nd or
31st of a month. All five live companies begin books on 1 April 2026, despite
the year in Sachin Infra's display name. Only the intentional before-books bill
uses 31 March 2026. No fixture changes a company's books date.

The source complexity baseline is the two scanned invoices and accompanying
e-way bills in `packages/sample_bills/`. Each synthetic bill includes 4–6 lines,
trade discounts, HSN/SAC references, PO/GRN/LR/DMR numbers and dates, repeated
totals, excluded previous balances/deposits, a receipt stamp and a corroborating
second page. Five bills per company are image-only scans with mild skew.
All documents and payment details are explicitly synthetic.

## Demo configuration and verified results

Leave all five companies open and unlocked. Use **2 September–31 October 2026**
for Source Discovery, then select the individual `bills/` folders in Bill Entry.
This period exposes 21 vouchers per company, including the historical duplicate,
correction baseline and one inventory purchase. Earlier history remains in Tally.
The complete April–October verification export contains all 250 seed vouchers.

The real platform context serializer produces 16 reference files totalling
6,762,242 bytes for the recommended period. Including the largest generated bill,
each child session fits at 7,086,014 bytes and 17 files, within the 8 MB / 45-file
limits. All five companies with the full April–October history produce 10,349,385
reference bytes and exceed that limit; use the recommended period for this demo.

| Company | Planned masters verified | Vouchers verified | Individual bills |
| --- | ---: | ---: | ---: |
| Pradeepraj Infra | 59 | 50 | 15 |
| Sachin Infra (2025-2026) | 59 | 50 | 15 |
| Second Test Company | 59 | 50 | 15 |
| Test Company | 59 | 50 | 15 |
| Third Tally Company | 59 | 50 | 15 |

Discovery and native saves succeeded with password-protected companies already
unlocked, data in three separate folders, and repeated folder-local company
numbers. Closed-company and same-name/wrong-GUID probes were held. No product
process-control or installation-path logic was needed. The final explicit seed
rerun found zero missing objects, created nothing and returned only duplicates.

Evidence under the package's `evidence/` includes `baseline.json`,
`seeded-snapshot.json`, `first-adapter-proofs.json`, `verification.json`,
`demo-period-snapshot.json`, `audit.json`, and timestamped native import requests
and acknowledgements. The full exports contain 223–224 records per company:
these include predefined masters and native company metadata. Tally also updates
derived group flags and voucher-type numbering/previous-narration fields as a
normal effect of creating children and vouchers; the before/after audit records
those changes. Every seeded voucher's date, type, ledgers, amounts and inventory
allocations was compared with the plan.

## Coverage and expected outcomes

| Bill ID | Case | First run expectation |
| --- | --- | --- |
| 01–07 | Cabin, plant spares, steel, aggregate, hire, freight, cement | Seven unique saves; split CGST/SGST, IGST, zero tax and different rates |
| 08 | Exact historical bill | Duplicate; no new voucher |
| 09 | Changed version of a historical bill | Correction held for a decision |
| 10 | Absent supplier | Create-this-ledger decision; deliberately unseeded |
| 11 | Printed `QA18 Pioneer` fits two supplier masters | Supplier unclear; no write |
| 12 | Separate round-off allocation | Unsupported structure; no flattened write |
| 13 | 31 March invoice before books begin | Before books begin; preserve the source date |
| 14 | Supplier's inventory practice and stock receipt | Manual entry; no flattened inventory |
| 15 | Scan of bill 01 | Together, 01 and 15 produce exactly one save |

`scripts/bill_entry_fixtures.py score RUN_ID PACKAGE` supports these cases.
Use `--rerun` after resolving decisions and saving new bills. Replay bypasses
extraction and paid sessions; it is an adapter/workflow check, not an AI score.
Do not run a paid worker and replay against the same run concurrently.

Each company receives 59 fixture masters (QA18 names, alphabetic MKQA unit symbols): creditor and purchase
groups; ten suppliers (including two ambiguous names); seven purchase heads;
seven tax ledgers; bank, cash, customer and supporting ledgers; projects,
units, locations, stock classifications and twelve items. Fifty seed vouchers
span June–September: 30 accounting purchases, two inventory purchases, eight
payments, two each of receipts/sales/journals/contras and one each of debit and
credit notes. New October bill references remain absent for real workflow tests.

## Regenerate and seed

Use the repository's Node/Python runtimes. Install the existing desktop connector
dependencies with `npm ci --prefix connectors/desktop`; the seeder resolves its
XML parser from that package, without a separate root installation.
Development PDF generation needs `reportlab`, `pypdf` and `pypdfium2`; these do
not become application dependencies. Generate into a fresh directory only:

```sh
python scripts/prepare_tally_demo.py --snapshot BASELINE.json --output NEW_PACKAGE
node scripts/seed_tally_demo.mjs NEW_PACKAGE
node scripts/seed_tally_demo.mjs NEW_PACKAGE --apply
```

The baseline is a complete `discoverClientContext` snapshot covering the live
companies. First create one simple `MKQANos` unit in any company through Tally
(formal name `QA Pieces`, three decimal places). The seeder requires an
exported unit created by this installation before importing inventory masters.
It retains native fields, replaces the name, and removes native identity fields
when cloning the template. The seeder defaults to a dry-run, validates the plan before
writes, and checks every company GUID. It creates only missing objects and
refuses incompatible existing definitions. It never alters existing masters
or vouchers. Every native import records its intent and response separately;
an uncertain import is never automatically repeated. Explicitly rerun after
read-only reconciliation to continue a partially applied seed.

The first historical purchase in each company is saved through the actual
`saveTallyBill` protocol 3 path with pinned company, ledger and voucher-type
references, then immediately replayed to prove duplication prevention. The
remaining history is imported natively. Final discovery verifies every amount,
ledger, date and native inventory allocation. Native receipts, before/after
snapshots and adapter proofs live under the package's top-level `evidence/`.

The initial unit imports failed and left five exception records. Tally's own
unit form then rejected both `QA18 Nos` and `QA18Nos` as invalid symbols, while
the all-letter `MKQANos` saved successfully. Reimporting or deleting the exception
objects through XML caused native crashes. With the operator's authorization,
the five failed QA18 records were cleared through Import → Exceptions, a native
alphabetic unit was created, and all five companies were reopened through Tally.
This was a one-off operator recovery using computer use, not product behavior.
No password was added to the repository, fixtures or importer.

The seeder now rejects digit-bearing unit symbols before any write and requires
a valid native template with distinct formal names and fresh native identities.
All 25 planned units and their dependent stock masters are live-verified.
Readback regressions also cover native whitespace-only empty sections and the
distinction between entered invoice ledgers and Tally's derived all-ledger view.
Reconcile after an uncertain import rather than automatically repeating it.

Checks:

```sh
python -m unittest discover -s scripts/tests -p test_tally_demo.py
node --test scripts/tests/tally-demo.test.mjs
node --test connectors/desktop/tests/*.test.js
```
