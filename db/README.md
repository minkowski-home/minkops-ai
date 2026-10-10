# OLTP migrations

Fresh installations execute **one reconciled baseline**, `migrations/0001_baseline.sql`.
It creates final tables, constraints, indexes, triggers, the updatable compatibility
view and the worker coordination singleton. It does not install demo/client data.

Existing databases retain all rows and migration history. `migrate.py` checks every
recorded checksum against the immutable `archive/pre-baseline` or active migrations,
applies missing legacy SQL to converge either previously released branch, and then
records adoption of the baseline. It never runs baseline CREATE statements over an
existing schema. Unknown history or changed checksums fail the entire transaction.
An advisory lock serializes migration runners. No production database reset is needed.

The archive is a **compatibility artifact**, not an active fresh-install migration
chain. Never edit or remove it while a supported installation can need it. New
changes go in new ordered files under `migrations/`; never squash again after this
pre-client baseline. Back up and rehearse adoption on a restored database before
deployment. Deployment and live database adoption remain paused for MIN-124.

Tests compare fresh and upgraded schemas and verify preserved paid sessions,
approvals, native write plans, company reservations, checksums and view updates.
