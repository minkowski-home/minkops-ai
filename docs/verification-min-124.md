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

Prepared versions: Source Discovery **0.7.2**, Bill Entry **0.8.1**, Windows
companion **0.5.1**. The successful Tally discovery used 0.7.1 before the final
Excel inventory instruction clarification; Excel discovery exercised 0.7.2.

## Automated and packaged checks

| Check | Result |
| --- | --- |
| Python platform, API, connector, DB and infrastructure suite with real PostgreSQL | 207 passed, 47 subtests |
| Web suite | 17 passed |
| Web lint, TypeScript and Vite production build | Passed |
| Native desktop connector suite on WSL | 56 passed |
| Native desktop connector suite on Windows | 55 passed; one symlink test skipped because Windows symlink privilege was unavailable |
| Windows HTTP smoke: real API/PostgreSQL, native folder refresh, restart/replay, device revocation | Passed |
| Windows 0.5.1 NSIS package build | Passed |
| Packaged executable login and local dashboard | Passed on Windows 11 Pro build 26200 |

The final local installer is
`C:\Users\gauss\Documents\Codex\min124-windows\apps\windows-app\release\Minkops Setup 0.5.1.exe`.
SHA-256: `23F35C3D3762BB202074E0DD3860B721F374211ABC2CB721FC62BC8848E8296B`.
Building and launching it does not establish installed-upgrade compatibility.

The native regression tests were first observed failing for the defects above,
then passed after the fixes. They cover unexpected company trailers, formatting
whitespace, typed numeric loads, genuine reference changes versus padded IDs,
and preservation of uncertain-import state across readiness failures.

## Live local workflows

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

Run `scripts/verify_discovery_context_live.py` or
`scripts/verify_discovery_excel_live.py` from WSL with `DATABASE_URL` ending in
`/minkops_min124_live`, `AUTH_DEV_MODE=1`, the existing server key configured,
`MINKOPS_WINDOWS_ROOT`, `MINKOPS_WINDOWS_NODE` (the executable's WSL path) and
a separate `MINKOPS_LIVE_DATA` checkpoint directory for each flow. Do not use
Python optimization: verification rejects `python -O`. `--resume-saves` on the
Tally script explicitly reconciles approved interrupted saves. Do not erase
checkpoints to retry a paid session implicitly.

Raw local evidence is intentionally untracked: WSL
`apps/solution-api/data/min124` and `apps/solution-api/data/min124-excel`, and
Windows `C:\Users\gauss\Documents\Codex\min124-windows\evidence\min124`.
Retain it for the remaining acceptance checks. Do not commit model credentials,
device credentials, native company exports or private workbook rows.
