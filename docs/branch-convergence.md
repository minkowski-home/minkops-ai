# Shared architecture with the complete Bill Entry application

This records the historical `platform-ai/bill-entry-architecture` consolidation,
subsequently merged into `main`. Current discovery/attention work continues on
`accounts/discovery-context`; follow README for the current product contract.
There is one Accounts queue, hosted lifecycle and installation path.

## Retained source revisions

| Previous branch | Retained tip | Archive tag |
| --- | --- | --- |
| `apps/windows-app` | `c3b050c6c7de1e1fef412e12242c87487fe9a933` | `archive/2026-10-07/windows-app-before-convergence` |
| `platform-ai/workflow-architecture` | `a5acde2f2721fd5ce807ac21d8e7a6d2424110c3` | `archive/2026-10-07/workflow-architecture-before-convergence` |
| `employees/bill-entry` | `3dc6552eb3d2570cc413bf9ec2ff0b3edd4ceb5e` | `archive/2026-10-07/bill-entry-before-convergence` |

Bill Entry's seven commits were replayed onto the architecture branch, then its
domain preparation/validation/write checks were moved into registered Accounts
handlers. The original native adapters, desktop runtime, Windows shell, bill
skills, output schemas, and reconciliation checks are retained. Only workflow
descriptors additionally declare installed handlers/presentations/capabilities.
Archive tags preserve the original histories before retiring the branch names.
No merge commit or pull request is needed for this consolidation.

Retained behavior includes independent per-bill extraction/recovery, partial
approvals, clarification/rejection, company-scoped financial reservations,
duplicate/backfill/correction handling, Excel saved-byte verification, Tally
ledger readback, periodic-discovery compatibility, native catalog export, and
the installed app's local-demo/tray behavior. Mock-client remains Tally-only for
Bill Entry; Excel remains available to client compositions that permit it.

## Database upgrade from either predecessor

1. Back up the database and stop API/workers/companion dispatch during the
   revision change. Preserve paid-session IDs, pending intents and receipts;
   do not relaunch outstanding work simply to change branches.
2. Run `uv run --all-packages python db/migrate.py` with the intended
   `DATABASE_URL`. The runner verifies archived checksums, applies missing
   convergence bridges, and adopts the final baseline without rebuilding data.
   See [baseline and preserved upgrades](../db/README.md).
3. Validate and dry-run the intended client installation using the authoring
   CLI, then install with a verified administrator. Preserve existing settings
   and status. If a destination preference conflicts with client policy, change
   that specific preference through the prior authorized settings path before
   installing; production installation fails atomically instead of resetting it.
   Demo seeding retains the previous explicit mock-client Tally-only transition
   and is only for isolated development databases.
4. Build/start the API, UI and native companion from the same revision. Resume
   stored runs/receipts through existing recovery contracts; verify pending
   financial saves before allowing additional writes to the same destinations.

The original two `0009` filenames and `0010` remain byte-identical. The migrator
already keys versions by the full filename stem, so their numeric prefix
collision does not duplicate a version. The real conflict was an original
Bill Entry foreign key/ALTER against `account_runs` after the architecture made
it a view. The additive `0008z` bridge runs before both original `0009` files,
temporarily restores the **same table's name**, and `0011` restores
`workflow_runs` plus the updatable `account_runs` view with its parent column.
The full migration is one locked transaction; no intermediate schema is exposed.
Existing foreign keys retain their table OIDs and every historical row remains.

Fresh databases and upgrades from either predecessor have regression coverage.
Tests pin original migration checksums and create isolated schemas directly,
so they still run after branch deletion and in a shallow checkout.

Application rollback requires deliberate compatibility review: a former worker
must not claim new non-Accounts definitions. Keep the migrated schema rather
than dropping shared tables or resetting history. Restore an archive tag in a
new recovery branch; do not move the consolidated branch backward.

## Verification

Run the full Python suite against an isolated migrated, demo-seeded database:

```sh
uv run --all-packages pytest platform/tests apps/solution-api/tests connectors/tests db/tests apps/corporate-website/api/tests -q
npm --prefix apps/solution-web test
npm --prefix apps/solution-web run build
npm --prefix apps/solution-web run lint
npm --prefix apps/windows-app test
npm --prefix apps/windows-app run build
```

The retained Bill Entry integration suite exercises authenticated PostgreSQL
launch/review/native receipts, concurrency, partial failure, correction and
duplicate handling. Architecture tests separately prove temporary/default
definitions, immutable client bindings, batch policy propagation and input-hash
rejection before paid execution. Upgrade tests cover both predecessor schemas,
fresh/repeat migration, preserved status/results/session IDs and view writes.

Live checks use a disposable database, synthetic documents/workbooks, and the
explicitly authorized Tally test company. Native Windows HTTP verification
checks folder refresh, restart/receipt replay, company export and revocation.
Production deployment, signing, a fresh-device installation matrix and
screen-reader auditing remain outside this reconciliation.

On 7 October 2026, the combined backend suite passed **168 tests and 45
subtests**; 17 web tests, TypeScript/Vite production build and zero-warning ESLint
passed. All 31 native tests passed on Linux; actual Windows passed 30 with only
the catalog-symlink creation case skipped for OS privileges (covered on Linux).
The Windows-local x64 NSIS build completed using the existing lockfiles and
Electron version. The test installer is unsigned; its SHA-256 is
`99dc9aada5dd576ff4c7ac79d1d0e1e34418d9afca50b685cf288ed2853deaf5`.

Live hosted discovery/extraction -> review -> Excel save/readback passed with
formulas and unrelated sheets preserved. A two-bill hosted Tally batch exercised
parallel sessions, one ambiguous-input clarification/retry without replaying the
successful sibling, approval, actual Windows/Tally saves, receipt replay,
duplicate detection and observed-identity correction/readback. The synthetic
correction was restored to its approved amounts; all 10 pre-existing vouchers
were unchanged. Paid environments closed successfully. Native Windows HTTP
folder/restart/replay/company-export/revocation checks passed. Browser checks
show the installed Tally-only policy and completed live Excel/Tally tasks at
desktop/mobile widths and in all four themes, without console errors or
horizontal overflow. These are local proofs, not a production deployment.
