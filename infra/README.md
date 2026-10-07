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
The registered Windows companion also reads schema metadata and reconciles
approved Tally writes. Business reasoning remains in OpenAI-hosted environments;
no customer-machine Codex executor is planned.

Build the production API image from the repository root:

```sh
docker build -f infra/solution.Dockerfile -t minkops-solution:review .
docker run --rm minkops-solution:review python -m minkops_api.install_workflows mock-client --validate-only
```

The same image runs `python -m minkops_api.accounts_worker --drain` as a bounded
Cloud Run Job. Transactional generations coalesce immediate wakes and an hourly
Scheduler recovers lost dispatches. See
[deployment, website migration and MIN-123 closeout](../docs/deployment-min-123.md)
for the deployed Myndral-style topology and CAD 15 hosting envelope. Hosting sites
are assigned by the explicit operator deploy script. Audit scripts read resource
metadata/metrics without retrieving secrets or customer database rows.

See [Accounts desk setup and limits](../docs/accounts-desk.md) and OpenAI's
[hosted environment guide](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted).
Production deployment and database restore are verified; remaining device/demo
release gates are recorded separately. Local processes alone do not establish
deployment health. Use the documented owner-operated deployment scripts until a
repository-bound OIDC pipeline and production approval environment are installed.
