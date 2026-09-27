# Engineering architecture

## Core model

Minkops is organized around business workflows. A workflow is the unit that
defines and executes a process from input through verified outcome. It can use
ordinary Python, a model call, and concrete tools as needed.

An **AI Employee** is a product catalog abstraction. It groups workflows and
provides customer-facing name, description, and availability. It has no
independent runtime, prompt, tool implementation, or business logic.

An **agent** is a bounded autonomous reasoning loop inside a workflow. Use one
only when the workflow needs iterative reasoning and tool selection. A fixed
sequence of steps is a workflow, not an agent.

A **skill** is reusable procedural knowledge supplied to model calls. Keep
instructions beside the first workflow that needs them. Extract a skill when
multiple workflows reuse the same knowledge.

A **tool** is a bounded callable operation. A **connector** implements access
to an external system and can expose its tools. A separate capabilities layer
is unnecessary until workflows need provider substitution, discovery, or
permission grouping.

## Where things live

- `workflows/` — reusable Python workflow implementations. Keep a workflow
  local to its application or solution until a second caller makes reuse real.
- `solutions/<id>/` — client-specific workflow composition and configuration:
  mappings, policies, prompts, employee catalog choices, and connector
  declarations.
- `connectors/` — implemented provider integrations and their concrete tools.
- `platform/` — shared runtime infrastructure such as persistence, tenancy,
  approvals, and job execution when those needs become concrete.
- `apps/` — deployable product entry points; keep HTTP and UI concerns here.
- `warehouse/` — the dbt warehouse and its own project lifecycle.
- `packages/` — small shared contracts or assets that have multiple callers.

Do not create directories for concepts without a concrete implementation or
reuse need. In particular, AI Employees do not need backend folders; skills
and agents are selective patterns rather than mandatory layers; and a handful
of Python functions do not make a reusable module.

## Example target: PDF bill to Excel

The workflow receives a bill, extracts structured fields, validates them,
checks for duplicates, applies the client's purchase-register mapping, obtains
approval when policy requires it, writes the row through the Excel connector,
and verifies the result. PR Infra's workbook columns and supplier rules live in
`solutions/pr-infra/`. Invoice extraction instructions remain beside the
workflow until another workflow reuses them. Supplier resolution becomes an
agent only if it needs iterative evidence gathering.

The AI Employee shown in the console merely exposes this workflow alongside
other available workflows.
