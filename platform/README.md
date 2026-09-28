# Platform

Put Minkops-owned, customer-independent application services here when they
have concrete implementations. The Agents API owns the Codex harness, agent
session orchestration, context compaction, and recovery. Do not rebuild those
features in this directory.

The application still needs a thin integration boundary: create and resume
sessions, correlate sessions and turns with Minkops runs, observe turn outcomes,
serve customer-visible progress, and apply tenancy, permissions, approvals, and
audit rules. For self-hosted environments, it must also arrange executor
provisioning, connection, reconnection, shutdown, and durable retrieval of files
and results. Put provider deployment definitions in `infra/`.

Keep employee workflow definitions in `employees/`, customer configuration in
`solutions/`, and custom external-system adapters in `connectors/`. Add a
platform module only when implementation and callers make its boundary clear.
