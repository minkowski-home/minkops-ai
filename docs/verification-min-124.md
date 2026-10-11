# MIN-124 verification: discovery context

Date: 2026-10-10. Branch: `accounts/discovery-context`.

This is predeployment evidence, not a deployment sign-off. Production deployment
was explicitly paused by the owner. MIN-124 must remain In Progress until its
remaining acceptance checks below have evidence.

## Implemented design and corrections

Version 2 discovery pins complete company-scoped Tally masters and period-limited
vouchers, plus structural Excel projections and reviewed context. Excel discovery
does not upload business rows or cached formula results. Buyer company identity
and field evidence remain distinct from vendor identity. Partial collection and
hosted-input budget failures cannot authorize dependent writes. Legacy pinned
runs retain their original contract.

Live exports exposed whitespace text nodes, native DayBook company trailers,
typed company numbers and padded ALTERID strings. The connector now accepts
those native representations while validating company identity and preserving
record contents. Restart uses numeric `/LOAD` arguments. A readiness failure
after an uncertain import preserves the ambiguity flag so a subsequent explicit
resume reconciles instead of blindly importing again. Workflow instructions now
state the validated evidence-key and Excel inventory coverage contracts.

Conflicting guidance was reconciled in Accounts Desk, Source Discovery, Bill
Entry and deployment documentation. The MIN-123 deployment record remains a
historical record; it does not imply these new versions are deployed.

Prepared versions: Source Discovery **0.7.2**, Bill Entry **0.9.0**, Windows
companion **0.6.0**. The earlier mixed-company and Excel proofs below used Bill
Entry 0.8.1 and companion 0.5.1. Their Tally discovery used 0.7.1 and their Excel
discovery used 0.7.2; retain that distinction when assessing release coverage.

The current product contract removes accounting editors and correction prompts,
adds shared auditable attention and native one-click supplier creation, and keeps
best-guess review pending after saving. Runtime choices are available to tenant
members; saved tenant/employee settings stay admin-only. Independent bill sessions
retain four worker lanes and per-session context budgets. Fresh installs use one
reconciled baseline; archived upgrades retain released SQL/checksums and paid runs.

## Automated and packaged checks

| Check | Result |
| --- | --- |
| Python platform, API, connector, DB and infrastructure suite with real PostgreSQL | 221 passed, 48 subtests |
| Web suite | 17 passed |
| Web lint, TypeScript and Vite production build | Passed |
| Native desktop connector suite on WSL | 60 passed |
| Native desktop connector suite on Windows | 59 passed; one symlink test skipped because Windows symlink privilege was unavailable |
| Windows HTTP smoke: real API/PostgreSQL, native folder refresh, restart/replay, device revocation | Passed |
| Windows 0.6.0 NSIS package build | Passed |
| Earlier 0.5.1 executable login and local dashboard | Passed on Windows 11 Pro build 26200 |
| Current 0.6.0 executable launch / installed upgrade | Pending: automatic approval review rejected the executable launch as blocked by policy |
| Current attention UI: Done persistence, grouping/sorting, pending refresh, 390px layout | Passed against local API/PostgreSQL; no horizontal overflow |

The final local installer is
`C:\Users\gauss\Documents\Codex\min124-windows\apps\windows-app\release\Minkops Setup 0.6.0.exe`.
SHA-256: `88C8FA93D7322910A7AF596D13531268973BC024BE8FD74615E9D5F0E872729C`.
Building it does not establish launch or installed-upgrade compatibility.

The native regression tests were first observed failing for the defects above,
then passed after the fixes. They cover unexpected company trailers, formatting
whitespace, typed numeric loads, genuine reference changes versus padded IDs,
and preservation of uncertain-import state across readiness failures.

## Live local workflows

### Current decision contract (0.9.0 / 0.6.0 adapters)

Confirmed Tally discovery 0.7.2: `b799c326-05ae-4129-85d7-9da31111b496`.
Bill run `6bee543b-ab30-4016-b311-02a8164fe2ac` completed a reviewed, independently
read-back voucher and receipt replay. Only Test Company was loaded for this run;
it does not replace the earlier two-company proof. A new-supplier paid run
`95dcff63-3efc-4b8c-94d9-b4a85e364700` retained complete evidenced bill values.
The ordinary `attention.supplier` decision created a native Sundry Creditors
master, verified its GUID/parent, continued that same bill and read back the 117
voucher. Explicit attention Refresh then verified the external resolution.
Both paid runs used gpt-6-luna; no values were entered through an app editor.

Excel discovery `5d388c45-e708-441e-a6a8-5512bb8433c4` and Bill Entry 0.9.0
`73200403-e8d7-406d-b2c8-0d839ba0a241` passed on a separate copy of the Excel-authored
named-table fixture. The initial discovery proposed a reference role; that result
is retained. A fresh explicit Excel configuration review confirmed the table's
destination role through the normal mapping-confirmation API. This changes
workflow configuration, not bill values. The native save appended
`MIN124-EXCEL-7f914bac` once for 300, expanded A4:F5 to A4:F6, preserved the private
original row and G5:G8 formulas, and replayed receipts without another write.
Every discovery projection ZIP entry was checked for private row-canary absence.

The automation ran through Minkops' API, hosted worker and production Windows
adapters. Browser automation checked UI decisions only; it did not substitute for
Minkops' extraction, Tally entry or native recovery implementation. The packaged
0.6.0 shell itself has not been launched. Multilingual handwriting accuracy and
the full live fault matrix remain unproven; automated mocks are not live proof.

### Earlier discovery-context integration evidence

Only synthetic, authorized fixtures were used. Existing server credentials were
used for hosted Source Discovery and Bill Entry with **gpt-6-luna**. Model
credentials were excluded from native subprocess environments. Workflow work
ran through the real API, worker, review, native job and receipt paths against
the dedicated `minkops_min124_live` database; the Windows adapters operated on
real Tally and an Excel-authored workbook. This is local integration evidence,
not hosted production evidence.

### Tally

One TallyPrime instance loaded numeric companies 100000 and 100001. Test Company
and Second Test Company contained shared synthetic supplier/purchase masters,
accounting history and a native inventory voucher. Collection preserved native
inventory, batch and accounting allocations; custom UDF preservation has
automated coverage but no live custom-UDF fixture in this run.

Confirmed discovery: `72fc7000-057d-42aa-8d64-eb2229287ddd`.
The paid mixed-company batch used the same invoice number and supplier for two
different buyers, with amounts 101 and 202. Both company writes completed with
verified receipts and exactly one matching voucher per company. Receipt replay
and an explicit resume of an interrupted approved write did not add duplicates.
A prior pinned discovery missing a required master held the affected company
instead of selecting the other company's master.

Real lost-acknowledgement tests passed: applied import reconciled as duplicate;
absent import returned attention without replay; a different existing amount
returned correction without import. Their evidence is in `recovery-ack-*.json`.

### Excel

The real workbook contained named table `MIN124Bills`, headers on row 4 and
shared formulas G5:G8 outside the table. Every projected ZIP entry was checked
for absence of private row canaries. The projection retained headers, named-table
metadata and translated formulas.

Confirmed discovery: `20e05856-8450-4e5d-afa4-a243aba82d2d`.
Paid Bill Entry: `c5d70599-2437-4b57-9781-ec3baaadc6c8`.
Native save appended invoice `MIN124-EXCEL-89e17afd` for 300 exactly once,
expanded the table from A4:F5 to A4:F6, preserved the original row and all four
formulas, and completed receipt replay. Both COM and full workbook readback
verified those results. The API's required destination-PC refresh was performed
before the bill run. Completed checkpoint replay passed without a new paid run.

Excel verification temporarily registered the core Bill Entry definition only
in the disposable DB and restored the mock-client composition afterwards.
A separate calculated-table-column fixture failed visibly with attention; it is
preserved as `unsupported-calculated-table.xlsx`, not claimed as supported.

## Failed attempts and remaining acceptance

Initial synthetic unit/import prototypes produced a Tally memory-access dialog
and inventory import exceptions. A unit and inventory history were subsequently
authored through native Tally screens and collected successfully. No matching
Windows crash event was found; the dialog alone does not establish its cause.

Paid attempts that emitted invalid evidence keys, omitted selected Excel tables,
or failed in the hosted runtime were retained as failed runs. Invalid proposals
were rejected before confirmation. The prompt contract corrections and explicit
retries produced the passing results above.

Controlled Tally termination during collection and after import restarted the
observed process but encountered lost-settings/Educational Mode/licence readiness
handoffs. These are **not** successful unattended restart tests. Earlier raw
`recovery-masters.json` and `recovery-import.json` retain failed assertions from
before the fixes; automated regression tests establish the code corrections,
but the full live fault matrix still needs another run in a ready environment.

Before MIN-124 can be Done:

- Finish live termination/recovery checks at probe, masters, vouchers, preflight,
  import and readback, including explicit reconciliation after the native licence
  handoff. Never replay an uncertain import automatically.
- Complete remaining live negative cases required by the issue, including
  ambiguous buyer selection and locked workbook behavior. Automated coverage
  does not replace their requested live evidence.
- Verify the minimum-supported Windows device and installed companion upgrade,
  pairing, background/tray lifecycle and compatibility with the production API.
- Resume authorized production deployment of API/web/worker/workflow definitions
  and companion, apply compatible additive migrations if required, then verify
  deployed HTTPS and both workflows with the deployed versions.

## Reproduction and evidence

Run the Python suite with `TEST_DATABASE_URL` pointing at a disposable PostgreSQL
database using a role allowed to create test databases:

```sh
.venv/bin/python -m pytest platform/tests apps/solution-api/tests connectors/tests db/tests infra/tests -q
```

`scripts/prepare_discovery_context_demo.mjs` explicitly requires
`MINKOPS_TALLY_TEST_COMPANIES` and `MINKOPS_LIVE_EVIDENCE`; create `MINTestNos`
through Tally once before preparing fixtures. `scripts/verify_tally_recovery_live.mjs`
requires one observed Tally instance with both numeric loads, an explicit
`MINKOPS_TALLY_TEST_COMPANY`, an evidence directory and a named fault stage.
These opt-in scripts modify only explicitly selected companies; fault stages
deliberately terminate the observed native process.

Run `scripts/verify_discovery_context_live.py`, `scripts/verify_bill_decisions_live.py`
or `scripts/verify_discovery_excel_live.py` from WSL with `DATABASE_URL` ending in
`/minkops_min124_live`, `AUTH_DEV_MODE=1`, the existing server key configured,
`MINKOPS_WINDOWS_ROOT`, `MINKOPS_WINDOWS_NODE` (the executable's WSL path) and
a separate `MINKOPS_LIVE_DATA` checkpoint directory for each flow. Do not use
Python optimization: verification rejects `python -O`. `--resume-saves` on the
Tally script explicitly reconciles approved interrupted saves. Do not erase
checkpoints to retry a paid session implicitly.
The decision proof uses a previously confirmed Tally checkpoint. For a separate
Excel fixture, set `MINKOPS_EXCEL_FIXTURE_ROOT` to its Windows folder; the proof
reviews the known table's destination role before confirmation.

Raw local evidence is intentionally untracked: WSL
`apps/solution-api/data/min124` and `apps/solution-api/data/min124-excel`, and
Windows `C:\Users\gauss\Documents\Codex\min124-windows\evidence\min124`.
Retain it for the remaining acceptance checks. Do not commit model credentials,
device credentials, native company exports or private workbook rows.
Current decision evidence/checkpoints are separately retained in
`apps/solution-api/data/min124-philosophy` and `data/min124-philosophy-excel`.
