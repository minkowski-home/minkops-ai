# Minkops.ai

### Product Vision
**Automation first; one-click decisions; manual work in the original tools.**
Minkops completes what it can truthfully automate. It never becomes an accounting
data-entry screen or a correction-prompt chat. Exceptions use short labels and
clear bill/file/voucher/cell identifiers, with contextual buttons such as
**Do nothing**, **Best guess write**, or **Create this ledger** when supported.
Do nothing preserves an attention item without writing. A best-guess write stays
pending human review even after a verified save. Manual changes happen in Tally,
Excel or the original system. Detailed diagnostics stay in internal audit records.

Attention is shared across workflows and employees, tenant-scoped and durable.
Members with access can mark items Done or request Refresh; every action records
its actor. Refresh completes items only from verified external resolution or
an edit after Minkops' write. Viewing an unchanged record cannot prove review.
Parallelize independent AI steps with bounded concurrency; preserve authorization,
ordered writes, idempotency and recovery. See [attention and decisions](docs/attention.md).

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

**Canonical architecture:** Skills and authorized MCP/REST tools drive the
OpenAI-managed Codex harness. Minkops supplies the product experience and a thin
control layer for access, durable runs, approvals, recovery, and verified writes.
This is the selected architecture for all new workflow work. The previous
workflow implementation remains Git history, not a parallel methodology to
preserve. Existing deterministic adapters and checks remain where they enforce
real integration or correctness requirements.

`main` contains the consolidated workflow and Windows companion architecture;
the earlier `platform-ai/bill-entry-architecture` branch was merged and removed.
See [branch convergence and upgrade](docs/branch-convergence.md) for the
retained source revisions, migration paths, verification, and recovery.


### Workflow methods and current scope

Execution method and environment hosting are separate choices. Minkops uses
**OpenAI-hosted Agents API environments**. Python and terminal commands inside
that hosted sandbox are not execution on the customer's machine. Self-hosted
Codex executors are not part of the current refactor.

| Method | Current implementation | Development direction | Not introduced yet |
| --- | --- | --- | --- |
| REST/MCP | Preferred product direction; Accounts does not currently bind business-system MCPs to its sessions. | Let skills compose existing authorized tools; keep access and consequential-write policy enforceable. Add a binding only for a concrete workflow need. | New SaaS/Tally integrations or a general connector catalogue. |
| Local execution | Browser-granted Excel saves and the Windows tray companion refresh selected folders, save approved Excel bytes and reconcile approved Tally Purchase vouchers. Web users can request bounded work on their connected PC. Codex Python runs in an OpenAI-hosted sandbox. | Keep native adapters bounded by explicit grants, approval and destination readback. | Customer-machine Python/terminal execution, general remote shells, or self-hosted Agents API environments. |
| Upload → modified → download | Selected file snapshots enter the hosted sandbox. Accounts returns approved bytes through the browser adapter to the existing file; users need no replacement-workbook download. | Evaluate skill-generated working copies in the hosted environment, retaining independent validation and approval. | A mandatory manual download/re-upload journey or replacing proven Excel safeguards before evaluation. |
| Computer use | Outside the current product scope. | Keep it in mind when assessing workflows whose tools lack adequate APIs or file access. | UI automation, computer-use permissions, or a computer-use runtime. |

The implementation provides reusable run controls and lifecycle boundaries,
complete versioned workflow skill bundles, and business regression checks.
Employee/client installation and workflow dispatch now use validated definitions
and shared services. See [workflow authoring and installation](docs/workflow-authoring.md)
for the CLI, Python extension points, and current integration boundaries.
Skill-generated workbook editing is a later evaluated pilot. New execution
methods are separate work. See
[the architecture and evaluation guide](docs/workflow-refactor.md).

Accounts Source Discovery now collects reusable full Tally masters, period-scoped
vouchers and reviewed client notes, with Excel confined to headers and formula
structure. Bill Entry pins this context, scans all selected bills, and saves
approved native entries by company. Tally retains bookkeeping; Minkops controls
entry, review and recovery. See [Source Discovery](docs/source-discovery.md) and
[pending Windows deployment](https://linear.app/minkops/issue/MIN-124).

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
or registered Windows companion applies approved Excel changes to a granted local folder;
the companion also reconciles approved mock-client Tally Purchase vouchers. See
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
publisher yet; the app polls durable state. Production uses Firebase Hosting,
Cloud Run and an isolated PostgreSQL database. See [deployment and MIN-123 gates](docs/deployment-min-123.md)
for verified hosting, cost controls and remaining device/demo checks.
Customer manifests in `solutions/` describe composition.

`apps/windows-app` supplies the Windows 10/11 x64 shell for that shared UI,
tray execution, native folder grants, and client-PC Tally/Excel source discovery.
Bill entry uses that discovery with shared approve/hold/reject/edit review,
independent parallel bill sessions and verified, idempotent destination saves.
See [Bill entry setup and demo verification](docs/bill-entry.md).
See [Source discovery setup and catalog contracts](docs/source-discovery.md).
See [Windows app setup and recovery](docs/windows-app.md). The mock-client
release candidate has been installed and visually checked on the current Windows
PC, including shared web review and tray execution. Scheduling remains MIN-121;
signing and broader Windows/device coverage remain distribution work.

For a local manual test, start the OLTP database and run migrations and the
demo seed as described in [db/README.md](db/README.md). Start the API with a
`DATABASE_URL` and `AUTH_DEV_MODE=1`, then start `apps/solution-web` with
`VITE_API_TARGET` pointing to the API. The seed prints the local demo password.

See [engineering architecture](docs/engineering-architecture.md) for ownership
and [infrastructure](infra/README.md) for the hosted boundary.
