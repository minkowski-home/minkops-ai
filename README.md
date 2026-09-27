# Minkops.ai

Minkops automates practical business work through preset workflows that fit a
customer's existing tools and processes.

## Architecture

- `apps/` — deployable web and API entry points.
- `workflows/` — shared Python business workflows, added when a workflow is
  reusable across applications or solutions.
- `solutions/` — client-specific workflow composition, mappings, policies,
  prompts, connector selection, and UI configuration.
- `connectors/` — concrete integrations with external systems. Add one when
  there is an implementation, not just a planned provider.
- `platform/` — shared, customer-independent runtime infrastructure.
- `warehouse/` — the dbt reporting warehouse.
- `packages/` — small shared contracts and product assets.
- `db/`, `infra/`, and `docs/` — database bootstrap, deployment configuration,
  and current engineering guidance.

## Product and execution model

An AI Employee is a product abstraction that groups workflows for customers.
It owns catalog and presentation metadata; it does not own business execution.

A workflow is the durable business execution unit. It defines the process,
validates inputs and outputs, and invokes concrete operations. Client-specific
workflow behavior belongs in that client's solution. A workflow that only
serves one application may live with that application until reuse justifies
moving it into `workflows/`.

Tools are bounded operations. Connectors provide the concrete external-system
integration; keep a tool beside its connector when it is only useful through
that integration. Skills are reusable procedural knowledge for model calls;
keep one-off instructions with their workflow. Agents are reserved for
autonomous reasoning loops used inside a workflow. Do not add a separate
capabilities layer unless provider substitution or dynamic tool resolution
requires it.

## Repository boundaries

Keep the Python execution architecture independent from the product's
TypeScript UI. Do not create one backend package or directory per AI Employee.
The dbt warehouse is a distinct subsystem at `warehouse/`. Do not create a
catch-all directory for small Python functions.

The shared solution web/API applications serve multiple solutions. Client
specific UI and configuration should compose through `solutions/<id>/` rather
than copying an application.
