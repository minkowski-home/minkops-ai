# Solutions

A solution composes the shared Minkops platform, reusable modules, and external
connectors for one customer. It may declare customer-specific workflows, rules,
prompts, and UI configuration. It must not copy `apps/solution-web` or
`apps/solution-api`.

## Start a solution

1. Create a new, lowercase solution identifier with `solution.ts`.
2. Declare the connector contracts there. Every solution receives the shared
   starter workspace; add a `web/src/App.tsx` only when it needs a bespoke UI.
3. Add customer-only workflows, rules, and prompts beneath that solution as
   they are implemented.
4. The shared host resolves a solution at runtime through `/<solution-id>/...`.
   Local development defaults to `pr-infra`; use, for example,
   `/mock-client/dashboard` to inspect the fixture.

`mock-client` is a local development fixture, not a customer deployment. Its
manifest demonstrates configuration overrides without owning the starter UI.
Connector entries are declarations only: each must be implemented under
`connectors/` before it can be enabled in a deployed solution.
