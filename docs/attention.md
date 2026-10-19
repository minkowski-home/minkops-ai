# Attention and one-click decisions

README's Product Vision and AGENTS.md are the canonical product rules. Manual
accounting edits belong in original systems, never in Minkops. Runtime choices
remain available to members; saved tenant/employee settings require an admin.

`attention_items` is shared tenant-scoped platform state, independent of any
workflow handler. Workflow adapters attach identifiers and trusted destination
targets. `attention_events` preserves short internal explanations and actors for
authorization, deferral, native failures, refresh and manual/verified completion.
The UI shows filenames, short labels, status and contextual buttons; audit logs
and extraction evidence explanations are not a user-facing reasoning transcript.
Bill labels come from exception codes, whether the model or a deterministic
server check raised them, such as "Ledger unclear", "Missing supplier", "Before
books begin" or "Tally changed". They no longer depend on message wording.
Verified duplicates and repeated batch inputs are recorded as internal notes, so
they never ask for attention.
The warehouse is future work; current audit records live in PostgreSQL.

Bill Entry also supplies one plain-language reason sentence to each review row
and Attention item. Typed exception/native hold codes select the sentence;
structured supplier identifiers may add context, and detailed model/native
diagnostics stay internal. Existing items without a stored sentence use their
typed short label to select a deterministic fallback. Do nothing preserves the
input's code and reason. The per-run unsaved-bills CSV uses these same sentences
and repeats the existing file-level Attention ID for multi-bill inputs; it does
not introduce per-bill Attention items or change Done/Refresh semantics.
Confirmed discovery catalogs also remain authoritative PostgreSQL snapshots.
Exact company GUIDs, masters and write contracts need deterministic lookup; a
future knowledge/vector index may aid retrieval but cannot authorize destinations.

Any member with tenant access can mark an item Done or request its external
refresh. Bill writes retain the original operator's authorization. Refresh uses
the already granted PC and exact server-owned target, not a new resource grant.
Missing/offline destinations and unresolved identities stay pending. Unsupported
workflows can create attention items and use manual Done; automatic refresh needs
a domain-specific evidence adapter. Current adapters cover Tally vouchers/masters
and PC-bound Excel rows. A browser-only workbook requires manual Done.
Grouping and sorting happen before pagination (200 items per page). Bulk refresh
queues at most 200 eligible pending items per click, rotating by last check;
offline and unsupported items remain available for manual Done.

Decisions name one bill. A file holding several invoices gets a decision per
bill, and its attention item closes only when every bill from it is settled.
Each bill input has one item per run and kind. Finalizing or re-aggregating a
run only restates its holds, so an operator's Done survives a sibling's recheck.
A new hold event reopens a Done item with its current reason: a destination
refusal (including a Retry save refused again), a correction, an interrupted
save, a save-time validation failure or a rechecked input. Stopping a batch
opens items under the batch run only, including bills its children had read
before aggregation; bills that were never read open none.
Do nothing never writes, retains a source identifier in attention and permits
other bills to continue. It is final for that run: the input is recorded as
deferred data, not a run-level finding, so exception-only saves of its siblings
continue, later decisions in the run stay valid and the run can complete. Best guess write accepts an existing supported proposal,
with the same required values, ledger identity and native verification checks.
After verified save, its exact voucher/row fingerprint becomes the review
baseline. It remains pending until manual Done or a changed, valid destination
observation. An unchanged record cannot demonstrate review. A verified save
completes a separate blocked-write event when one exists; the best-guess review
event remains pending. Ambiguous identities, multiple matching records, missing
mandatory data or unsupported accounting
structures cannot be overridden by the button. Observed corrections can be
authorized with one click; the application selects the operation, not the user.

Retry save replaces Best guess write when a supported bill was held by its
destination, not by its interpretation. Examples are Tally refusing a voucher
date, an unconfirmed import, ambiguous existing vouchers, an unavailable PC or
another run reserving the same bill. After the operator fixes Tally or reconnects
the PC, the run's original operator re-sends the same proposal. It goes through
the normal validation and native read-first save, so an equal voucher is
skipped and a different one becomes a correction decision. As a technical retry
it opens no best-guess review. An existing voucher with different values
remains a correction decision through Best guess write.

Create this ledger is currently bounded to a missing, evidenced supplier for a
supported non-tax Purchase bill. It creates a Sundry Creditors master through
Tally's native import, verifies the master and queues that bill's normal save.
The verified new master extends only the authorized continuation's reference
snapshot; other runs must refresh Source Discovery. Statutory/tax setup, billwise
opening balances and arbitrary company creation have no supported automatic
contract and remain manual. Never offer a creation button without enough
verified information. Import uncertainty requires explicit reconciliation;
consequential jobs are not reclaimed automatically when a lease expires.
After a failed/uncertain supplier import, an explicit Refresh can verify the
previously authorized master and continue the bill without another master import.
Recheck bill uses refreshed discovery to rescan an unresolved input without a
human correction prompt; it retains the input snapshot and saved siblings.

Bill Entry uses durable per-bill hosted sessions and four bounded worker lanes.
Hundreds of selected inputs become independent child runs; hosted 45-file/8-MB
budgets apply to each bill plus its complete lookup files, not to the aggregate
batch. Tally writes stay serialized on the companion. Local AI subagents are a
future execution capability, not part of the current hosted implementation.

Production deployment remains paused. Native restart/licence handoff and device
acceptance gaps remain tracked in [MIN-124 evidence](verification-min-124.md).

Statement Entry opens one file-level exception summary with counts. Row details and exception CSV live in the task; it does not create one Attention item per bank row. Write ready rows, Retry save checks and Do nothing preserve the immutable native manifest. Correct parsing/routing problems in the original statement or Tally and start a refreshed run. A possible existing untagged voucher or uncertain import stays held for reconciliation.
