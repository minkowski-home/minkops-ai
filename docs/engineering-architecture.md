# Engineering architecture

## Product model

An **AI Employee** is a customer-facing collection of business workflows.
`employees/<employee-id>/` is the canonical home for that collection. A
**workflow** defines a business goal, valid inputs, expected outputs, and
completion checks. Place it under its owning employee at
`employees/<employee-id>/workflows/<workflow-id>/`.

The workflow does not prescribe every reasoning step. The Agents API's Codex
harness may perform most of the work: reason, choose tools, use skills, search
the web when appropriate, and delegate subtasks. Keep a deterministic check
for a result that must be correct before it is accepted. Share a workflow
across employees only when there is a real second owner; avoid copied versions.

`solutions/<client-id>/employees/<employee-id>/` holds customer-specific
enablement and configuration. It references the canonical employee workflows
and can supply mappings, instructions, policy, permissions, and approval rules.
It does not copy the workflow or create another application.

## Execution boundary

OpenAI runs the **harness**, including agent sessions, model/tool loop,
compaction, and recovery. Minkops plans to run the **environment** on
Minkops-controlled infrastructure through the Agents API's `self_hosted`
option. An executor (`codex exec-server`) in each isolated environment connects
to its corresponding session. The particular GCP service or other provider has
not been selected. Self-hosting the environment is not self-hosting the model
or harness.

Use built-in Agents API capabilities and available OpenAI tools, skills,
plugins, web search, and MCP connections where suitable. A plugin packages
skills and/or MCP configuration; it is not a requirement for every workflow.
Use a custom connector, MCP server, or application function only when the
business system or access rules need one. A service-origin MCP connection can
run without local executor code; an environment-origin MCP connection runs
from the executor's environment. Tool availability is configured and scoped
for the session, not implied by a directory or a console manifest.

The Minkops application owns the product boundary: authentication, tenant and
workflow selection, authorized tools, approvals, progress shown to customers,
run-to-session correlation, verified outcomes, and audit records. It also owns
self-hosted environment provisioning and cleanup, plus durable retrieval of
output files. Those concerns belong in `apps/`, `platform/`, and `infra/` as
implementation requires. `connectors/` holds integrations Minkops implements.
The root `warehouse/` remains a separate dbt reporting subsystem.

## Current state and first implementation

This is a scaffold decision. There is no implemented employee workflow,
Agents API session manager, self-hosted executor deployment, or approved GCP
target in this repository. The existing image-to-Excel API uses a direct
Responses API call and remains in place. PR Infra's manifest declares console
identity and connector intent, not deployed tool access.

For the first real workflow, specify its employee, business contract, client
configuration, allowed tools, result check, and evaluation examples. Then
integrate the Agents API and one isolated executor environment. Validate a
real session, tool behavior, output, and cleanup before generalizing the
runtime or adding more provider infrastructure.

## References

- [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview)
- [Agents API architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture)
- [Self-hosted environments](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)
- [MCP connections](https://developers.openai.com/api/docs/guides/agents-api/tools/mcp)
- [Plugins](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins)
