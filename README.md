# Minkops.ai

## Product Vision
Minkops offers AI Employees that carry out practical business workflows in a
customer's existing tools and processes.
In simple terms, we are building something as close as possible to ChatGPT Work desktop app, except replace prompting with one-click workflows.
The application should involve a well-designed combination/selection of the following main types of execution modes:
- REST/MCP: Where integration is available, prefer this mode. E.g. Read invoices from one system and create records in another.
- Local Execution: Use local Python installation, create scripts and run on user's machine, or run terminal commands. All this should be fully abstracted from the user behind our beautiful UI.
- Chat-mode like Upload->Modified->Download process: We want to avoid this as much as possible. Always prefer the above two methods unless the workflow genuinely calls for this.
- Computer Use: Minkops controlling the app's interface. This is not in scope currently, may be introduced later.

Keep these four methods in mind when designing every workflow. Choose the
available method that fits the customer's tools and permissions; a workflow
may combine methods. First check what skill-driven Codex, OpenAI-provided tools,
and existing MCP/REST integrations can already do. Add custom code only for a
demonstrated access, correctness, or product gap.

### Workflow methods and current scope

Execution method and environment hosting are separate choices. Minkops uses
**OpenAI-hosted Agents API environments**. Python and terminal commands inside
that hosted sandbox are not execution on the customer's machine. Self-hosted
Codex executors are not part of the current refactor.

| Method | Current implementation | Current refactor direction | Not introduced yet |
| --- | --- | --- | --- |
| REST/MCP | Preferred product direction; Accounts does not currently bind business-system MCPs to its sessions. | Let skills compose existing authorized tools; keep access and consequential-write policy enforceable. Add a binding only for a concrete workflow need. | New SaaS/Tally integrations or a general connector catalogue. |
| Local execution | The browser saves approved Excel bytes to a granted folder; Codex runs Python in an OpenAI-hosted sandbox. | Preserve the browser write adapter and its verified in-place saves. Keep file access separate from skill instructions. | Customer-machine Python/terminal execution, a desktop executor, or self-hosted Agents API environments. |
| Upload → modified → download | Selected file snapshots enter the hosted sandbox. Accounts returns approved bytes through the browser adapter to the existing file; users need no replacement-workbook download. | Evaluate skill-generated working copies in the hosted environment, retaining independent validation and approval. | A mandatory manual download/re-upload journey or replacing proven Excel safeguards before evaluation. |
| Computer use | Outside the current product scope. | Keep it in mind when assessing workflows whose tools lack adequate APIs or file access. | UI automation, computer-use permissions, or a computer-use runtime. |

The current refactor implements reusable run controls and lifecycle boundaries,
complete versioned workflow skill bundles, and a regression baseline against the
preserved Accounts implementation. Skill-generated workbook editing is a later
evaluated pilot. New execution methods are separate work. See
[the refactor scope and evaluation guide](docs/workflow-refactor.md).

### Where development belongs

Most product development belongs in `apps/`: workflow launch/configuration,
resource connection, review, progress, and customer-facing outcomes. Workflow
procedures belong in `employees/` as skills, prompts, schemas, examples, and
supporting scripts, with customer bindings in `solutions/`.

Keep `platform/` a thin shared control layer for the requirements a workflow
actually has: authorized resources, durable runs, approvals, recovery, and
verification. OpenAI owns the AI execution loop. Keep reusable application
logic out of app transport code, and external-system/file adapters in
`connectors/`. A skill is guidance; it does not enforce permissions or prove
that a consequential write is correct.

## Repository map

- `employees/` — shared employee definitions and the workflows they offer.
- `solutions/` — customer composition under
  `solutions/<client-id>/employees/<employee-id>/`, plus each solution's shared
  application manifest.
- `apps/` — deployable web and API entry points shared across customers.
- `platform/` — Minkops-owned concerns around Agents API sessions, access,
  approvals, outcomes, and audit records as implementations are added.
- `connectors/` — integrations Minkops must implement or mediate itself.
- `infra/` — local OLTP Compose and hosted runtime guidance.
- `warehouse/` — reserved for a separately designed warehouse; currently empty.
- `packages/`, `db/`, `design/`, and `docs/` — shared contracts and assets,
  versioned OLTP migrations, design sources, and engineering guidance.

## Execution model

The [Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview)
supplies the Codex harness for reasoning, tool use, session orchestration,
compaction, and recovery. Accounts desk uses **OpenAI-hosted execution environments**
with `gpt-6-luna`. Minkops persists tenant-scoped runs and approvals; the browser
applies approved Excel changes directly to a granted local folder. See
[the Accounts desk guide](docs/accounts-desk.md) for contracts and recovery.

Use OpenAI-provided capabilities when appropriate, including web search and
available skills, plugins, and MCP tools. Keep customer data access and
consequential actions bounded by permissions and customer policy. Implement a
custom connector, function tool, or plugin only for a concrete gap. A workflow
states the business outcome and how to verify it; the harness may perform most
of its execution.

The shared app now supports verified accounts and tenant membership, employee
and workflow settings, task observations, and four selectable brand themes.
`mock-tenant` exposes Source discovery and Bill entry as executable workflows,
alongside the older image-to-Excel test. Agent results, reviews and verified local
writes appear in task progress and timelines. The outbox has no production
publisher yet; the app polls durable state. Deployment remains separate from
local execution proof. Customer manifests in `solutions/` describe composition.

For a local manual test, start the OLTP database and run migrations and the
demo seed as described in [db/README.md](db/README.md). Start the API with a
`DATABASE_URL` and `AUTH_DEV_MODE=1`, then start `apps/solution-web` with
`VITE_API_TARGET` pointing to the API. The seed prints the local demo password.

See [engineering architecture](docs/engineering-architecture.md) for ownership
and [infrastructure](infra/README.md) for the hosted boundary.
