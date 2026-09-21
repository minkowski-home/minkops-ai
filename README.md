# Minkops.ai

Minkops.ai is a suite of autonomous AI employees that handle customer intake, operational monitoring, administration, analytics, and communication through a unified knowledge graph, policy model, and orchestration layer. A typical customer can "hire" any set of agents, which work together (fully-intercommunicating and accessing company knowledge as real human employees would) perfoming actual job duties - each agent tends to replace one real human employee with disjoint skills. Each fleet of agents (for an organization) runs continuously 24x7 instead of one-time jobs.


## Layout

- `apps/` — shared deployable surfaces: `solution-web`, `solution-api`, and the corporate website.
- `platform/` — customer-independent infrastructure. The AI decision library and runtime live in `platform/ai/`.
- `modules/` — reusable business capabilities. The existing dbt project is `modules/reporting/warehouse`.
- `connectors/` — concrete external-system integrations; add an integration here only when it exists.
- `solutions/` — customer-specific composition: configuration, workflows, rules, prompts, and UI choices. See `solutions/README.md`.
- `packages/` — deliberately shared code packages, including the brand tokens and solution composition contract.
- `db/` — operational schema bootstrap. `db/init/` is not a migration history yet.
- `infra/` and `docs/` — deployment assets and cross-cutting documentation.

The same solution web/API applications are composed with a selected solution at
build time. For local console work, run `VITE_SOLUTION=mock-client npm run dev` from
`apps/solution-web`. Do not fork the applications for a customer-specific UI or
connector selection.

**Agentic Stuff**: We shall utilize OpenAI/Anthropic APIs aggressively. As of Sep 2026, both provide a comprehensive set of APIs for almost everything that Codex/Claude Code does, our product can be thought of as Codex-like app, but for low tech maturity teams avoiding prompting hell and providing with preset one-click workflows to automate their everyday routine.

### Legacy Agents
Not sure whether we shall continue with the individual agent style product anymore. To be decided. Current focus is on
preset workflows instead - use these named agents only where it really makes sense.

| Persona (at MH, not exposed anywhere else) | Agent Name | Agent / Tool                    | Description                                                                        | Domain          | Priority  |
|--------------------------------------------| ---------- | ------------------------------- | ---------------------------------------------------------------------------------- | --------------- |-----------|
| Bianca                                     | Ora        | Moodboard Generator             | Generates moodboards based on user defined aesthetics, products, style, theme etc. | Interior Design | Moderate  |
| Ryan                                       | Eko        | Social Media Handler            | Posts, engages, and manages the social media handle of the company                 | Generic         | Very High |
| Ethan                                      | Floc       | Content Creator (Ad/Email copies)| Generates marketing content based on brand kit and company knowledge              | Generic         | Very High |
| Devin                                      | Cruz       | Manager's Assistant             |                                                                                    | Fast Food       | Very Low  |
| Emily                                      | Hosi       | Front of the House              |                                                                                    | Fast Food       | Very Low  |
| Tony                                       | Prex       | Back of the House               |                                                                                    | Fast Food       | Very Low  |
| Jaina                                      | Kall       | Phone Call/Customer Support Rep |                                                                                    | Generic         | High      |
| Sarah                                      | Leed       | Lead Generation Caller          |                                                                                    | Generic         | Immediate |
| Kim                                        | Kim        | Store Manager's Assistant       |                                                                                    | Generic         | Low       |
| Mark                                       | Insi       | Business Analyst                |                                                                                    | Generic         | Low       |
| Nathan                                     | Imel       | Email Handler                   |                                                                                    | Generic         | Immediate |

### Brief Repo Structure

- `apps/` — deployable entry points: shared web host, shared API, and corporate site.
- `solutions/` — one folder per client/use case; composes UI configuration, workflows, rules, and connector declarations. `mock-client` is a fixture; `pr-infra` is the first real solution.
- `platform/` — client-agnostic infrastructure. Today: AI decision graphs and their runtime; later auth, tenancy, audit, jobs, etc.
- `modules/` — reusable business capabilities, such as reconciliation, reporting, document extraction, or scheduling.
- `connectors/` — protocol/vendor integrations: WhatsApp, banks, Excel, OpenAI/Anthropic, and so on. They contain authentication/client mapping, not client policy.
- `packages/` — small reusable code packages/contracts, such as the solution manifest types and brand primitives. If there's conflict in `design/` and brand-kit in `packages/`, `design/` takes precedence.
- `db/` — database bootstrap setup. It is intentionally not migrations yet: it creates a fresh local database.
- `design/` — the shared visual system the starter workspace and client-specific UIs build upon.
- `infra/` - deployment (docker-compose, cloud related, etc) and all.

#### `solutions/` sub-directories
They are PR Infra’s client-specific layer, currently empty by design:

- `schemas/` — structured record shape extracted from images.
- `prompts/` — PR Infra-specific extraction/review instructions for models.
- `rules/` — validation, exception, and human-approval policies.
- `mappings/` — mapping approved fields to Excel columns.
- `workflows/` — orchestration wiring reusable modules and connectors into the WhatsApp → review → Excel flow.
- `solution.ts` — the manifest: identity and enabled connector declarations.
- `README.md` — boundary guidance.

There is no `web/` folder yet because PR Infra currently uses the shared starter workspace. Add `web/` only if it needs UI beyond that default console.