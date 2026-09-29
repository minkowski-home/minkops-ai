# Infrastructure

`compose.yml` runs only the local OLTP PostgreSQL database. The old Airflow
and warehouse stack was removed as part of the clean database reset. It does
not deploy an agent executor.

## Self-hosted Agents API environments

Minkops intends to run its own isolated execution environments, potentially
on GCP, while OpenAI runs the Codex harness. Each Agents API session created
with `environment.type: "self_hosted"` gets an environment ID and requires its
own connected `codex exec-server`. The executor runs commands and accesses
workspace files and local MCP servers inside Minkops-controlled compute. It
connects outbound to OpenAI; Minkops owns provisioning, dependencies, access,
reconnection, file retention, and cleanup. See the
[self-hosted environment guide](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted).

The deployment target, isolation boundary, image, and lifecycle controller
remain design decisions. Do not treat the present Compose services as an agent
runtime or deploy a shared executor for all customers by default. Keep API
credentials and customer system credentials outside repository files and
agent-readable workspace content. Register skills and plugins supported by
the Agents API in the session environment when needed; use service-origin MCP
connections for reachable remote servers when that is the simpler path.
