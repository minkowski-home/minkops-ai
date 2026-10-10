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
The warehouse is future work; current audit records live in PostgreSQL.
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

Do nothing never writes, retains a source identifier in attention and permits
other bills to continue. Best guess write accepts an existing supported proposal,
with the same required values, ledger identity and native verification checks.
After verified save, its exact voucher/row fingerprint becomes the review
baseline. It remains pending until manual Done or a changed, valid destination
observation. An unchanged record cannot demonstrate review. A verified save
completes a separate blocked-write event when one exists; the best-guess review
event remains pending. Ambiguous identities, multiple matching records, missing
mandatory data or unsupported accounting
structures cannot be overridden by the button. Observed corrections can be
authorized with one click; the application selects the operation, not the user.

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
