# MIN-124 release verification: discovery context

Verified 11 October 2026 on Windows 11 Pro build 26200 with real TallyPrime,
Excel-authored workbooks, PostgreSQL and deployed HTTPS workflows. Production
deployment, merge into main and issue closure were explicitly authorized by the
owner. The Windows 10 device test is deferred by that authorization; Windows
10 compatibility remains in the application and packaging configuration.

## Released stack

| Component | Verified release |
| --- | --- |
| Source Discovery | 0.7.2, complete confirmed format-2 context |
| Bill Entry | 0.9.0, company-scoped decisions and verified native writes |
| Windows companion | 0.6.4, installed upgrade and public download |
| API | `minkops-solution-api-00006-4bj`, 100% traffic |
| API/worker source | `5cc541f98eebdfc7bde8dd6cc84093acd4d7711b` |
| API/worker image index | `sha256:daeed48d05507c509234d6b319724bbf155a3b7c951f91a186f1fd2ba6b88078` |
| Executed Linux/amd64 image | `sha256:a5978a71875f8bed5ce63aceb58248c46fcaaac9c51e6c04f3772e43c9dcfa5f` |
| Console hosting | `ff7945dbddcb59b9`, asset `index-qNgZCl6x.js` |
| Corporate hosting | `45c288c64c205406`, asset `index-NTQZyM_W.js` |
| Windows runtime source | `f6305af0f3892995a5df3b94202562009ef0fcca` |

Later changes affect native JavaScript, Windows packaging and release records;
the deployed Python implementation is unchanged. Registry inspection confirmed
that the executed platform digest belongs to the deployed image index. The API
and worker retain bounded pilot resources, production authentication, Secure
cookies and CSRF protection. Paid verification worker executions completed.

[Windows download](https://minkops.com/download): `Minkops Setup 0.6.4.exe`,
102,776,359 bytes. SHA-256:
`3444ca472a78a6d3638a074140652ce77e3b0cbabba5233f399859a69fd3c02f`.
The published installer was downloaded and its bytes/hash verified. It retains
the existing unsigned installer contract. Installed and packaged ASAR runtime
bytes match the compiled current-source bundle, SHA-256
`263dd9cc7ae00c6de03e4249f69bc6eb435b04fa22e10984fa56eb871b451e3f`.

Production migration was rehearsed against a restored backup before applying it.
Cloud SQL backup `1791702113875` succeeded; the private logical dump was restored
and checked. All seven original paid runs, their results, operator settings and
released migration checksums survived. The database moved from 27 to 29 public
tables; repeated migration passed. Runtime credentials cannot perform DDL.

## Corrections established by live evidence

- Fresh installations now define constraints directly in the sole baseline.
  Exact prior/current baseline checksums remain accepted for preserved upgrades;
  seven schema catalog comparisons matched. Obsolete shims/options/caches were
  removed, and workflow operator scripts moved from `infra/` to `scripts/`.
- Recovery waits for every observed numeric company load. Earlier readiness
  could return when only the first company became available.
- Detailed voucher export uses **Voucher Register**. Native DayBook ignored the
  configured dates on this installation. Empty periods, inclusive boundaries and
  a multi-chunk export now match independent native exports.
- Archive recovery rejects an occupied regular file without replacing it.
  Atomic publication still verifies existing package identity and hashes.
- Windows builds resolve the current workspace connector/runtime sources
  explicitly. npm's copied `file:` dependencies had put stale adapters into
  earlier installers. Versions 0.6.0–0.6.3 therefore do not establish the final
  runtime guarantees; 0.6.4 supersedes those candidates.

Regression tests were observed failing before the respective native fixes and
passing afterwards. Current recovery and packaging contracts are documented in
[the Windows app guide](windows-app.md).

## Native discovery and recovery

One TallyPrime instance loaded company 100000, **Test Company**
(`c216692a-0dae-4edf-ab34-4bc748d728d1`), and company 100001,
**Second Test Company** (`a708e67b-00a7-4a80-af85-ea2bc4a1134a`). Restart arguments
use these numeric numbers, never company GUIDs. The installed upgrade preserved
device `f36875e8-3311-46c3-bb77-e6dd2acc5b09`, signed-in account and dark theme.

Independent full XML comparisons found 198/195 undated masters and 13/5 vouchers
for 1–2 October before the final production writes. Every collected record
matched its native export, including nested inventory, batch allocations and a
real custom ledger UDF. A 1 October single-day export retained its vouchers;
2 October and 1 December exported zero. Synthetic vouchers on 1 September and
1 November established inclusive endpoints; the wide export contained 17 native
vouchers and matched across the 31-day chunks. Actual installed 0.6.4 discovery
`843663ba-3ef4-4141-a5bf-c50d75a04f2b` independently returned complete masters and
zero vouchers for 1 December in both companies.

Controlled process disappearance was exercised at probe, masters, vouchers,
preflight, import and readback. Each job allowed at most one restart. Where
Tally required Educational Mode/licence interaction, the operator completed the
native handoff and used explicit resume; this is not unattended licence recovery.
An applied import with lost acknowledgement reconciled as duplicate, an absent
import remained in attention without replay, and a different existing amount
required correction without import. HTTP 503, native XML rejection, a live
instance and missing startup identity produced diagnostics without starting a
second process. Multiple/uncertain-process, lease-expiry, partial-batch and
receipt-retry guards additionally retain automated coverage. No matching
Windows crash event established the cause of earlier native error dialogs.

All 12 deployed confirmed versions now match their authoritative server catalogs
and every manifest's sizes/hashes. Confirmation of the December run occurred
while the app process count was zero. After reconnect, queued versions archived
in confirmation order: `19ddb12b…`, `38486c51…`, `8bb95616…`, `998dece4…`,
`843663ba…`. Earlier controlled obstruction fixtures were preserved as evidence.
The final occupied-file check preserved its exact bytes, kept successors queued
and displayed Connected PCs attention while server copies remained ready.
After clearing only those fixtures, seven earlier valid packages stayed unchanged,
catch-up completed and the alert cleared. Identical refresh reused the previous
reviewed subjective notes without another interpretation session.

## Deployed Bill Entry and retained Excel proof

The deployed paid batch `ade093eb-946c-4df3-8411-4612401bf73e` pinned discovery
`49d6eddf-d375-46c9-ab7b-f28a433a9216`. Both independent scans persisted buyer GUIDs
before any native write. The same supplier and invoice `MIN124-PROD-59ee44c8`
saved once in Test Company for 629.39 and once in Second Test Company for 314.17.
Normal one-click **Best guess write** decisions preserved the tenant's review
policy. Both writes completed through installed 0.6.4 while its UI was closed.
Fresh independent native readback found exactly one balanced voucher per company.
Replay performed zero imports. Verified receipts:
`83587fbb-7eb0-41e2-8c9c-e89e6e88a6ab` and
`0cbb039d-5ec8-44b1-bd62-31faa701f13f`.
Best-guess items correctly remain pending human review after the verified saves.

Locked-company deployed inventory run `dda62cf4-0013-426d-aa4e-3ea3ea7c8078`
used the collected historical records and handed off unsupported stock/batch/
godown allocations with zero proposed writes and no native invoice. Its stock
alias lacked resolving Purchase history; the existing historical inventory
voucher was Sales. This is truthful negative lookup evidence, not a claim of
successful supported inventory entry. Current local paid runs also rejected
ambiguous (`00e49122-f5d1-487f-8c31-36c79523902c`) and contradictory locked buyers
(`14fb0079-dcf7-44d5-b70c-bcff4d43050e`) without writes. Real native unavailable
company, changed company GUID and stale ledger references each stopped before
import. Earlier one-click supplier creation retained its independently verified
117 voucher and supplier GUID/parent checks.

Unchanged Excel evidence was retained rather than repeating paid work:
discovery `5d388c45-e708-441e-a6a8-5512bb8433c4`, Bill Entry 0.9.0 run
`73200403-e8d7-406d-b2c8-0d839ba0a241`. The real Excel-authored named table grew
from A4:F5 to A4:F6, appended invoice `MIN124-EXCEL-7f914bac` once for 300 and
preserved its private original row and shared formulas G5:G8. Every projection
ZIP entry excluded private row canaries and cached results. Full workbook/COM
readback and receipt replay passed. Unsupported calculated-table columns stayed
in attention. A Windows sharing lock prevented replacement, preserving original
bytes and the recovery backup while removing temporary output.

## Validation and evidence retention

Retained cleanup validation: 235 Python tests/49 subtests with real PostgreSQL,
17 web tests, strict TypeScript/build checks and focused lint passed. Final native
source suite: 63/63 passed on Linux; 62 passed on Windows with one unavailable
symlink-privilege skip. The updated build script bundles successfully on both
systems; final NSIS packaging, installed upgrade and runtime-byte comparison
passed. Existing automated partial/oversize/export-budget guards remain intact.

Raw evidence is private and intentionally untracked: WSL
`apps/solution-api/data/min124*`, Windows
`C:\Users\gauss\Documents\Codex\min124-windows\evidence\min124-final`, and private
deployment checkpoints under `~/.local/state/minkops-deployment`. Native exports,
workbook rows, passwords and device credentials are excluded from Git and Docker
build context. Failed attempts remain preserved; paid checkpoints prevent
implicit reruns. Opt-in live verification scripts in `scripts/` require explicit
test companies and isolated evidence/database paths.
