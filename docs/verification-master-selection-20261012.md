# Native master selection and split-tax verification — 12 October 2026

The current parent is `platform-ai/complete-discovery-scope`. Source Discovery UI,
shared progress and Pause/Resume/Stop changes were already merged there; the
Source Discovery feature branch was removed after that successful merge. The
requested `platform-ai/bill-entry-connections-ui` merge is `ef123a9`.

This continuation adds evidenced canonical master selection, exception-only
execution, complete native historical allocations and separate tax allocations.
No customer-specific supplier or accounting mapping is added to runtime code.
Manual accounting corrections continue to belong in the original systems.

## Automated checks

- Python/PostgreSQL/API: **314 passed, 49 subtests passed**. Coverage includes
  cross-company/catalog references, stale identities, legacy compatibility,
  positive new-supplier outcomes, independent sibling decisions, conflicting
  duplicate versions, split receipts and older-client protocol rejection.
- Windows companion/desktop connectors: **80 passed**, no skipped tests.
  Coverage includes period bounds, nested native allocations, tax balances,
  separate import lines, exact readback, replay and uncertain acknowledgement.
- Shared web: **31 unit tests passed**, build and lint passed. The browser suite
  passed **3 tests**, including persisted file/default selections, review mode,
  destination PC ownership and connection checks. Browser fixtures intercept
  business APIs; the live proof below exercises the real installed companion.
- An intermittent worker test was reproduced deterministically: lanes could
  start before the coalescing lease was published. The lease now precedes submit.
  Independent diagnostics also survive a business rollback under the real
  PostgreSQL runtime row lock.

## Live proof and limitations

The installed companion collected complete masters for three loaded Tally
companies, with inclusive April–October voucher history and actual ledger and
inventory subcollections. Final comparison finds **12 routine synthetic bills**
with exactly one voucher per identity and correct supplier, date, expense and
amount; no missing-supplier or ambiguous fixture was imported. Final master /
voucher counts are **179 / 10**, **203 / 28**, and **206 / 41** respectively.

The first trial used a snapshot whose voucher root wildcard omitted nested
allocations. One synthetic Hindi bill was assigned the wrong expense ledger.
Its original failure evidence was retained, and that fixture was corrected
externally in Tally. After complete history collection and current-identity
exclusion guidance, an independent hosted reread selected the expected expense
and the installed companion verified the existing voucher as a duplicate.
The final 12/12 comparison describes the verified final destination, not perfect
first-attempt model accuracy.

Two current-period synthetic GST bills were read by the hosted workflow and
saved through the **installed 0.6.9 app** with separate CGST and SGST allocations.
Both have exactly four native lines: supplier, expense, CGST and SGST. Independent
readback verifies every amount and identity. A read-only reconciliation replay
returns **duplicate for both, with zero imports**.

The model incorrectly flagged those two synthetic bills as possible duplicates
of different invoice references. The existing audited **Best guess write** action
was used after checking the source references and mappings; separate human-review
attention remains pending by design. This proof demonstrates the native split-tax
contract, not unattended model success for those inputs. Workflow **0.11.1** adds
general guidance to preserve every invoice-reference token and examine competing
expense masters. Paid live sessions were pinned to **0.11.0**; the final guidance
change is covered by bundle validation and has not received another paid rerun.

Both original March bills remain held: Tally returned **“Voucher date is missing”**
for the supplied dates. Native inspection confirms no matching original voucher.
The Tally process did not disappear or restart. The office-cabin proposal also
needs its competing expense classification resolved before approval. No invoice
date, original master or real-company policy was changed to force acceptance.
The companion now distinguishes a rejected date from an unknown write outcome;
neither path automatically repeats an import. No successful original-bill save or
statutory GST filing readiness is claimed.

Full evidence, real PDFs and raw native exports remain in ignored local
`apps/solution-api/data/master-selection-final/`. Checkpointed scripts preserve
the failed trials and verified receipts; they must not be reused against an
unrelated or production company. No customer documents or API credentials are
included in these commits.

## Installed local build

- Application: **0.6.9**, verified from the installed `app.asar`, using the
  existing **Minkops Local Demo** profile and the same registered PC identity.
- Installer SHA-256:
  `9A7FBE29BA14A207C0257323A7AEABBA9800E512D03E60BFAE9C27B8BB93D878`.
- API / UI: loopback ports **8018 / 3018**. Desktop and Start Menu shortcuts
  start the local services and installed application together.
- Database: **minkops_parallel_local_20261011**, the freshest development history.
  The prior upgrade backup and other databases are preserved. The additional
  databases represent older baselines, restore checks and isolated validation
  rehearsals; they are not concurrent active production databases.
- Installed workflow: **Bill Entry 0.11.1**, mock-client variant **1.2.0**.
  Existing runs retain their pinned bundles. Split plans require protocol 2;
  older companions receive an update instruction rather than a flattened plan.
