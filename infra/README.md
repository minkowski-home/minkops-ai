# Infrastructure

`compose.yml` runs the local OLTP PostgreSQL database. The API and durable
Accounts worker are separate processes sharing that database. OpenAI provisions
the agent execution environment; Compose does not run a Codex executor.

Accounts desk creates per-run `openai_hosted` Agents API sessions with
`gpt-6-luna`, network access disabled, and required Python packages. Selected
files are supplied as tenant-scoped immutable snapshots. API credentials stay
outside agent-readable content. Results are persisted before hosted environment
cleanup; workers retry pending cleanup and retain session IDs for audit.

The browser applies approved Excel writes through a granted local folder. This
is a web adapter with synchronized snapshots, not fully local desktop execution.
The future desktop adapter can replace the file-access seam while retaining
approvals and verification. Self-hosted execution is no longer the selected
architecture for these workflows.

See [Accounts desk setup and limits](../docs/accounts-desk.md) and OpenAI's
[hosted environment guide](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted).
Production deployment, worker supervision and database retention policy remain
operational release work; local processes do not establish deployment health.
