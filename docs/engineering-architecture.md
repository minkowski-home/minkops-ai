# Engineering architecture

## Current product boundary

Skill-driven execution using the OpenAI-managed Codex harness and adequate
authorized MCP/REST tools is the canonical workflow architecture. New workflows
start with employee procedures, tool capabilities, and business contracts;
custom implementation follows only demonstrated gaps or enforceable guarantees.
The pre-refactor methodology is historical, with no parallel-maintenance
requirement. Existing deterministic adapters, checks, and non-agent application
services remain appropriate for their concrete integration and control roles.

OpenAI-hosted Agents API environments are the selected execution architecture.
Self-hosted Codex executors are outside the current refactor. Hosted sandbox
Python execution and browser-granted local file saves do not imply an agent
running on the customer's machine. The four workflow methods and their current
scope are described in [the product vision](../README.md#workflow-methods-and-current-scope).

Product development centers on `apps/`; workflow execution should maximize
employee skills, prompts, OpenAI-provided capabilities, and adequate existing
MCP/REST integrations. `platform/` supplies only shared control requirements
that are justified by actual workflows. Preserve the dependency direction
apps → platform → connectors, without recreating the managed harness or
prebuilding a general workflow engine.

`apps/solution-web` and `apps/solution-api` serve one shared application for
every tenant. A signed-in user belongs to a tenant as an admin or member.
Platform admins can manage any tenant; tenant admins manage their own. Other
members can view settings. Work email domains provide a verified discovery
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
outcomes. Each task has a status, progress, short summary, and event timeline.
The pane is adjustable on desktop. The four app themes use the locked brand
palette in `design/tokens/` and a per-browser preference.

## Persistence and events

`db/migrations/` is the versioned OLTP source of truth. Migrations are applied
transactionally with a checksum, and changed migrations are rejected. The
initial PostgreSQL schema starts clean: identity, membership, employees,
workflows, task observations, and an event outbox. Writes to observable task
state and settings insert outbox records in the same transaction. Accounts desk now has a durable database worker and OpenAI-hosted runtime.
The app polls task state; there is no production outbox publisher or message
broker yet. See [Accounts desk](accounts-desk.md) for run and write ownership.

`warehouse/` is intentionally empty. It has no schema, dbt project, or
pipeline; its design is reserved for separate work.

## Test fixture

`db/seed_demo.py` creates `mock-tenant` with sample employees, workflows, and
tasks for manual testing. Its image-to-Excel route is a mock-tenant-only test
workflow. PR Infra starts with zero employees and zero workflows. The two Accounts desk workflows are active for the mock tenant and execute
against explicit folder grants. Local fixtures do not imply a production release.
