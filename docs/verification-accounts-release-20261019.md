# Accounts release verification - 19 October 2026

Scope: MIN-125, MIN-126 and MIN-120. Staging is the integration branch; main is unchanged. All financial acceptance fixtures are synthetic and scoped to Test Company, GUID `f1a14ea6-4313-459c-91d0-03f3054c1226`.

## Deployment evidence

- API and worker immutable image: `sha256:db037fb10ed8a3dc0b94fa6ac671578f91ece56ecdb658a7bbc8b2ad30883794`.
- Console Hosting version: `sites/minkops-ai-console/versions/0e11f1a28e570743`.
- Corporate Hosting version: `sites/minkops-ai-prod/versions/ecc4bd91c7bb2363`.
- Installed and published companion: **0.8.0**, native plan protocol **4**. Installer remains an unsigned release candidate under the existing disclosure.
- Public installer downloaded independently: **102,867,070 bytes**, SHA-256 `342b68640c1ffec6e55e3ba57957508667c886a3d2135aa1cd2e89bee031eedf`. Both update-feed SHA-512 representations match the downloaded bytes.
- Runtime capacity remains 1 CPU / 512 MiB; worker selects one lane, one task, no automatic task retries. API remains min 0 / max 1 / concurrency 2.
- PRs [100](https://github.com/minkowski-home/minkops-ai/pull/100), [101](https://github.com/minkowski-home/minkops-ai/pull/101), [102](https://github.com/minkowski-home/minkops-ai/pull/102), [103](https://github.com/minkowski-home/minkops-ai/pull/103), [104](https://github.com/minkowski-home/minkops-ai/pull/104), [105](https://github.com/minkowski-home/minkops-ai/pull/105) and [106](https://github.com/minkowski-home/minkops-ai/pull/106) merged to staging. Worker capacity correction [107](https://github.com/minkowski-home/minkops-ai/pull/107) passed all three CI jobs and merged to staging as `f4d2e9428f309da0c87128d863fd4c30b6d4cb28`. Its tree is identical to the deployed and locally tested revision.

## Database and operator state

A consistent 19,734,876-byte PostgreSQL logical backup was restored into an isolated PostgreSQL 16 database. All 32 existing tables restored. Migration count increased from 24 to 26; a second application was idempotent and existing row counts were preserved. The additive production migrations and trusted workflow installations completed successfully.

The verified ordinary test operator password was rotated, prior sessions revoked, production login verified, and memberships retained. Credentials and rollback snapshots are stored outside Git in private local operator state.

PR Infra had no tenant or real source data. Its workspace was provisioned with Source Discovery and Statement Entry using the existing verified operator; no platform administrator grant or real business records were introduced. Its bank destinations and Other-side ledger remain unconfigured pending actual client data, as authorized.

## Automated verification

- Full Python suite: **499 tests and 52 subtests passed**.
- Native companion/connector suite: **110 passed**.
- Web: **47 unit tests**, production build and lint passed.
- Browser integration: **9 passed**, including actual metadata-only discovery shape, statement review, desktop/mobile layouts, exception-only bills, CSV, routing and defaults.
- New regressions reproduced before their fixes: native-only discovery must not apply hosted interpretation limits; aggregation must never decode child execution catalogs; configured worker concurrency reaches both bootstrap modes.

## Live acceptance

- Installed Windows 0.8.0 signed in and connected to the production synthetic workspace through the app UI.
- Native discovery collected all five open companies; full masters and the selected voucher period were retained. AI was disabled. A full fiscal-year catalog and a shorter bill-verification catalog both confirmed successfully after the native-only limit fix.
- Synthetic GST supplier `MIN126 Verified GST Supplier 20261018` created only in Test Company; complete native GSTIN, registration, state, place of supply, address and PIN readback passed.
- Initial native Payment 127.31 and Receipt 183.47 were independently read back; replay returned duplicate with exactly one tagged voucher of each kind. An acknowledgement/readback date mismatch was recovered without resending the uncertain Payment.
- Final UI statement upload, explicit discovered bank selection and workflow defaults were exercised in the installed app. The real production browser UI launched a statement preview with no page errors.
- Final statement run `b2b57ea6-2eb8-4a98-801d-353d62c962f8`: Payment 127.32 and Receipt 183.48 saved through the installed app. Independent native readback verified date, company GUID, voucher type, balanced ledger entries and exactly one tagged voucher per row (`...-00000035`, `...-00000036`). Unknown branch and broken running balance rows stayed held with plain reasons; the installed app's Do nothing action completed the run with two saved and two rejected rows.
- Installed-app Export CSV opened a native Save As dialog and downloaded a 489-byte UTF-8 BOM CSV containing exactly the two unsaved statement rows. It is byte-identical to the authenticated server export; private/no-store headers and cross-tenant 404 were checked.
- Native Windows setup uploaded a second file containing overlapping statement rows, selected both files and the discovered Test Company bank ledger, saved Only exceptions defaults, then launched run `f7939146-f094-4e36-8822-9fa3721fc9da`. It resolved all four repeated valid rows as already in Tally and held the two unknown-branch plus two invalid-balance rows. Independent native readback still found exactly one final Payment and one Receipt. The post-fix same-file run and dashboard quick run both completed with two duplicates and two rejected invalid rows, without another native import.
- Production gpt-6-luna scanned five genuine synthetic PDFs: three identical new-supplier issues, one clean existing-supplier bill and a non-invoice checklist. The clean bill saved automatically; the review showed only four exceptions and a collapsed saved count.
- The installed app previewed and confirmed **Create this ledger · 3 similar bills** for `MIN126 Final GST Supplier 20261019`, GSTIN `08AABCT2468P1ZR`. One ledger (`...-0000010b`) was created with native verification of Regular registration, Rajasthan/state 08, Rajasthan place of supply, source address and PIN 332001. All three authorized invoices then saved. Independent readback found exactly one Purchase voucher each for A/B/C/CLEAN (`...-00000039`, `...-00000038`, `...-0000003a`, `...-00000037`), dated 2 October, each 100 + CGST 9 + SGST 9 = 118 with exact ledger entries.
- Three per-item bulk audit events retain the same actor, trigger, preview token and scoped supplier identity. Replaying the same confirmation returned unchanged state: four write intents and three audit events. The dissimilar checklist stayed untouched.
- Bill Entry collapsed all four saved bills, displayed the checklist's plain reason, and its Do nothing handler completed the run while retaining manual Attention. The installed native Save As download is byte-identical to the server's 277-byte UTF-8 BOM CSV containing only that unsaved input. Private/no-store and cross-tenant 404 passed; a separate API export after deferral checks the durable decision.
- Final worker recovery completed all five paid scans with no lost/recreated inputs. The selected model remained gpt-6-luna; statement runs created no hosted sessions. No paid rechecks were launched. Runtime capacity stayed at the pilot limits. Provider turn responses returned no usage totals, so this evidence does not claim an independently audited dollar bill.
- Post-deployment recovery and dashboard quick-run acceptance passed on the final immutable API/worker image and console version. Release evidence and issue closure reference the tested staging pull requests.

Two pre-capacity worker executions reached the memory limit before creating any hosted sessions. Existing queued runs are recovered through the durable worker; they are not recreated. An extra unapproved statement preview from a UI navigation timeout was stopped through task controls.
## Concurrency correction during acceptance

The first separate same-file statement replay failed before dispatch with PostgreSQL `40P01` (run `552e4822-ef4a-47e4-9a8e-7ea86c06dbd0`). Database logs identified the cycle: a worker held the workflow row and waited for its write intent's device foreign key, while authenticated device polling held the device row and waited for that workflow. The transaction rolled back; no native voucher was imported for that failed run.

[PR 108](https://github.com/minkowski-home/minkops-ai/pull/108) changes device polling to a non-key update lock and ownership checks to key-share locks. Revocation retains an explicit exclusive lock; unique credential rotation stays exclusive. A real database regression reproduced the blocked approval before the fix, then passed while the poll transaction remained open. A separate regression checks revocation waits and rejects old credentials after completion. It passed all CI jobs and merged into staging as `afcbd6af07103e21dde2a98b154be34364ee7972`. Final API revision `minkops-solution-api-00016-gzm` and the worker are Ready on the immutable image above. Native Windows re-ran the same file as run `6af8cb82-a1e8-4185-bea1-061f7da04fde`: two duplicate rows, two held rows, no errors and no hosted session. Do nothing completed it with two duplicates and two rejected rows; no new vouchers were imported.

Merged task branches from PRs 100–107 were removed only after verifying their remote heads still matched their merged pull requests. Main and unrelated branches were preserved.

## Saved statement setup

Final Windows dashboard testing found that statement preferences incorrectly reused the bill-only file filter. [PR 109](https://github.com/minkowski-home/minkops-ai/pull/109) passes the workflow's CSV/XLSX pattern into the shared source/path selection helper. The existing bill default remains covered. A unit regression reproduced the lost preference before the fix; the browser regression restores a saved bank and statement after a file-ID refresh, then launches from the dashboard with the replacement ID. All 47 web tests, build, lint and all nine browser tests pass. PR 109 passed all CI jobs and merged into staging as `72b108c6a03e7b8b50bb458fdf04ba8fa5d759f6`; the final console version above contains that exact built revision.

The installed 0.8.0 app was reloaded after deployment. Native setup selected `statement-final.csv` and retained the discovered bank and Only exceptions options. Run `6af8cb82-a1e8-4185-bea1-061f7da04fde` completed after verifying two duplicates and rejecting the two invalid rows through Do nothing. The dashboard's Run workflow then launched `b6864b55-806c-41b1-a8c6-0a416bd8f5d9` directly, reusing the saved file, bank and options. It also completed with two duplicates and two rejected rows, no error and no hosted session. Final independent native readback again found exactly one tagged final Payment and Receipt, plus exactly one of each of the four Purchase invoices.

The overlapping two-file test was completed with its four verified duplicates and four rejected invalid rows. Superseded discovery-size and pre-fix deadlock Attention items were marked Done through the ordinary handler after successful replacements; original failed tasks and diagnostics remain auditable. Manual bill and statement exceptions retain their reasons. No unrelated historical Attention items were changed.
