# Platform

Put Minkops-owned, customer-independent application services here when they
have concrete implementations. The Agents API owns the Codex harness, agent
session orchestration, context compaction, and recovery. Do not rebuild those
features in this directory.

The application still needs a thin integration boundary: create and resume
sessions, correlate sessions and turns with Minkops runs, observe turn outcomes,
serve customer-visible progress, and apply tenancy, permissions, approvals, and
audit rules. Accounts desk uses OpenAI-hosted environments; provider deployment
definitions belong in `infra/`.

Keep employee workflow definitions in `employees/`, customer configuration in
`solutions/`, and custom external-system adapters in `connectors/`. The
installable `minkops_platform` package lives in `src/`; add modules there when
implementation and callers make their boundaries clear.

Accounts services live in `minkops_platform.accounts`: catalog validation, run
commands, persistence and the durable worker. `runtime.openai_hosted` handles
the SDK session lifecycle; employee prompts stay in `employees/`. Shared services
raise transport-neutral errors, which the API translates into HTTP responses.
