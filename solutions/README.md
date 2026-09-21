# Solutions

A solution composes the shared Minkops platform, reusable modules, and external
connectors for one customer. It may declare customer-specific workflows, rules,
prompts, and UI configuration. It must not copy `apps/solution-web` or
`apps/solution-api`.

## Start a solution

1. Copy `example/` to a new, lowercase solution identifier.
2. Change the exported `solution` manifest in `ui.ts` to select navigation,
   visible UI options, and connector contracts.
3. Add customer-only workflows, rules, and prompts beneath that solution as
   they are implemented.
4. Run the console with `VITE_SOLUTION=<identifier>`.

`example` is a local development fixture, not a customer deployment. Connector
entries are declarations only: each must be implemented under `connectors/`
before it can be enabled in a deployed solution.
