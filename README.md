# Minkops.ai

Minkops offers AI Employees that carry out practical business workflows in a
customer's existing tools and processes.

## Repository map

- `employees/` — shared employee definitions and the workflows they offer.
- `solutions/` — customer composition under
  `solutions/<client-id>/employees/<employee-id>/`, plus each solution's shared
  application manifest.
- `apps/` — deployable web and API entry points shared across customers.
- `platform/` — Minkops-owned concerns around Agents API sessions, access,
  approvals, outcomes, and audit records as implementations are added.
- `connectors/` — integrations Minkops must implement or mediate itself.
- `infra/` — local OLTP Compose and self-hosted executor guidance.
- `warehouse/` — reserved for a separately designed warehouse; currently empty.
- `packages/`, `db/`, `design/`, and `docs/` — shared contracts and assets,
  versioned OLTP migrations, design sources, and engineering guidance.

## Execution model

The [Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview)
supplies the Codex harness for reasoning, tool use, session orchestration,
compaction, and recovery. Minkops intends to run isolated **self-hosted
execution environments** on infrastructure it controls, potentially GCP. The
executor in each environment connects to the managed harness; self-hosting the
environment does not self-host the model or harness. The specific cloud service
and deployment design are still to be selected.

Use OpenAI-provided capabilities when appropriate, including web search and
available skills, plugins, and MCP tools. Keep customer data access and
consequential actions bounded by permissions and customer policy. Implement a
custom connector, function tool, or plugin only for a concrete gap. A workflow
states the business outcome and how to verify it; the harness may perform most
of its execution.

The shared app now supports verified accounts and tenant membership, employee
and workflow settings, task observations, and four selectable brand themes.
`mock-tenant` alone exposes image-to-Excel as a test workflow. There is no
production agent runtime or event publisher yet. The customer manifests in
`solutions/` declare composition intent, not deployed agent configuration.

For a local manual test, start the OLTP database and run migrations and the
demo seed as described in [db/README.md](db/README.md). Start the API with a
`DATABASE_URL` and `AUTH_DEV_MODE=1`, then start `apps/solution-web` with
`VITE_API_TARGET` pointing to the API. The seed prints the local demo password.

See [engineering architecture](docs/engineering-architecture.md) for ownership
and [infrastructure](infra/README.md) for the self-hosted boundary.
