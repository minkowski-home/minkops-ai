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
- `infra/` — deployment and self-hosted executor guidance; the current Compose
  stack serves local warehouse development.
- `warehouse/` — the separate dbt reporting project.
- `packages/`, `db/`, `design/`, and `docs/` — shared contracts and assets,
  database bootstrap, design sources, and engineering guidance.

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

The current `apps/solution-api` image-to-Excel route is an existing direct
Responses API path. It has not been migrated to the Agents API. The customer
manifests in `solutions/` currently select UI and declare connector intent;
they are not deployed agent or executor configuration.

See [engineering architecture](docs/engineering-architecture.md) for ownership
and [infrastructure](infra/README.md) for the self-hosted boundary.
