# Engineering architecture

## Current product boundary

Skill-driven tool sessions on the OpenAI Agents API are the canonical workflow
architecture. A session reasons over its document and calls Minkops's authorized,
read-only tools, which are MCP-shaped contracts, then proposes; Minkops checks every
proposal, owns review and performs every write. New workflows start with employee
procedures, tools and business contracts; custom implementation follows only
demonstrated gaps or enforceable guarantees. Earlier workflow implementations live
only in Git history.

Accounts desk sessions run with no hosted environment, so nothing executes on
OpenAI's side but the model. Self-hosted executors are out of scope, and
browser-granted local file reads do not imply an agent running on the customer's
machine. The four workflow methods and their current scope are described in
[the product vision](../README.md#workflow-methods-and-current-scope).

The Windows shell shares the web UI and adds an authenticated outbound companion
for bounded native work: folder snapshots, the read-only Tally sync, approved
voucher saves with readback, and verified GST supplier creation. Durable device/job controls live in `platform/`; native
filesystem/Tally adapters live in `connectors/`. The companion does not host or replace the managed AI harness.
See [Windows app architecture and recovery](windows-app.md).

Product development centers on `apps/`; workflow execution should maximize
employee skills, prompts, OpenAI-provided capabilities, and adequate existing
MCP/REST integrations. `platform/` supplies only shared control requirements
that are justified by actual workflows. Preserve the dependency direction
apps → platform → connectors, without recreating the managed harness or
prebuilding a general workflow engine.

`apps/solution-web` and `apps/solution-api` serve one shared application for
every tenant. A signed-in user belongs to a tenant as an admin or member.
Platform admins can manage any tenant; tenant admins manage their own. Other
members can view saved settings, choose per-run configuration and resolve
attention items they can access. Saved tenant/employee configuration stays
admin-only. Work email domains provide a verified discovery
hint, never automatic access. Invitations and approved join requests establish
membership, including for personal email addresses.

Each tenant owns employees, workflows, tasks, and its settings. A workflow can
reference multiple employees through `workflow_employees`; there is no agent
team entity. Employees and workflows have small declarative JSON Schema
contracts plus validated JSONB values. This supports different controls per
client without adding a database column or handwritten form for every setting.
The API authorizes each read and write against the requested tenant. Composite
foreign keys prevent links across tenants.

The dashboard displays the signed-in user's name and observable work. The
activity pane owns active tasks, attention requests, handoffs, and recent
outcomes. Each task has a status, progress and short summary; detailed events
stay in internal audit. The persistent [attention list](attention.md) spans all
workflows: new companies, statement questions and gaps, and practice questions.
The pane is adjustable on desktop. The four app themes use the locked brand
palette in `design/tokens/` and a per-browser preference.

## Definition installation and dispatch

Repository-owned employee definitions and client bindings install atomically
through the shared installation service and administrative CLI. Operator
settings/statuses survive reinstall; incompatible schemas are rejected. The
installed handler and presentation are separate from editable workflow
preferences. A future admin UI can call the same services.

A launch pins the definition version, the session bundle (model, reasoning effort,
service tier and instructions) and the mirror version of every company it reads. A closed
registry (`work.HANDLER_MODULES`) maps pinned handler keys to ordinary Python
modules, independently of workflow keys. Accounts keeps its business checks and
verified Tally write reconciliation in those handlers. The worker serves lanes
that follow each run item's session.

`runs`, `run_items` and `run_records` hold every run, with each item's sessions
(`item_sessions`), tool calls (`tool_calls`) and references (`item_refs`). The
retired pipeline's tables left with migration `0032`.

See [workflow authoring](workflow-authoring.md) for contracts, installation,
extension points, and migration/rollback guidance.

## Persistence and events

`db/migrations/` is the versioned OLTP source of truth. Migrations are applied
transactionally with a checksum, and changed migrations are rejected. The schema
covers identity and membership, employees and workflows, task observations, runs
and their native writes, desktop devices and jobs, shared attention, client
profiles, and an event outbox. Writes to observable task state and settings
insert outbox records in the same transaction. Accounts desk runs on a durable
database worker whose lanes follow tool sessions. The app polls task state; there
is no production outbox publisher or message broker yet. See [Accounts desk](accounts-desk.md) for run and write ownership.

`warehouse/` is intentionally empty. It has no schema, dbt project, or
pipeline; its design is reserved for separate work.

## Test fixture

`db/seed_demo.py` creates `mock-tenant` for manual testing, installs the
mock-client composition (Statement entry and Bill entry, both active) and adds
two example workflows in paused and planned states. It creates
no tasks; activity comes only from real runs. The local PR Infra tenant starts
with zero employees and zero workflows. Local fixtures do not imply a production
release.
