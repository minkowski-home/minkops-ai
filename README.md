# MinkOps.ai

Minkops.ai is a suite of autonomous AI employees that handle customer intake, operational monitoring, administration, analytics, and communication through a unified knowledge graph, policy model, and orchestration layer. A typical customer can "hire" any set of agents, which work together (fully-intercommunicating and accessing company knowledge as real human employees would) perfoming actual job duties - each agent tends to replace one real human employee with disjoint skills. Each fleet of agents (for an organization) runs continuously 24x7 instead of one-time jobs. 

### Test one run (Updated 2026-02-26)

**Prerequisites:** copy `services/ai-suite/.env.example` to `services/ai-suite/.env` and fill in `ADMIN_DB_URL`, `DATABASE_URL`, `MINKOPS_DB_PASSWORD`, and `PSQL_PATH` for your machine.

**Step 1 — Bootstrap** *(first time only, or after a fresh Postgres install)*

Creates the `minkops` app role, the `minkops_app` database if it doesn't exist, installs extensions, and sets default privileges. The password is passed at invocation time — never hardcoded. Safe to re-run.

```bash
psql postgres -v minkops_password=$MINKOPS_DB_PASSWORD -f db/bootstrap.sql
```

> If `psql` is not on your PATH, use the full binary path from `PSQL_PATH` in your `.env`.

**Step 2 — Seed the schema**

Drops all tables and recreates them. Run from the repo root or `services/ai-suite`.

```bash
cd services/ai-suite
seed-db
```

**Step 3 — Run an agent**

```bash
run-imel --email "Hi, I placed an order last week and haven't received a confirmation. Can you help?"
```

Or with the LLM:

```bash
run-imel --use-llm --email "Hi, I placed an order last week and haven't received a confirmation. Can you help?"
```

**What to watch for:**

- Step 1 → `NOTICE: Role minkops created.` (or "already exists" on repeat runs)
- Step 2 → `psql` prints all `CREATE TABLE` / `CREATE INDEX` lines cleanly, then Python logs `Seed complete for tenant_id=tenant_001`
- Step 3 auth error → bootstrap hasn't run yet, or `MINKOPS_DB_PASSWORD` doesn't match the password in `DATABASE_URL` — fix `.env` and re-run Step 1

**Important**

Initially, the graphs will be slightly more deterministic to ensure predictability and easier debugging. There will be more interrupts and agents will wait for human feedback before taking a final action. The database, DWH and systems must be designed in a way to use this human interaction data to train agents using RLHF to take decisions and learn from mistakes, leading to fully autonomous agents.

## Layout

- `apps/` — user-facing experiences; currently `apps/corporate-website` hosts the Minkops marketing site.
- `services/` — production and prototype services; `services/ai-suite` is the conversational/operational agent platform plus legacy notebooks and tooling.
- `infra/` — infrastructure plans and automation (currently contains a README placeholder but can grow Terraform, Kubernetes, or GH Actions artifacts).
- `docs/` — cross-cutting playbooks, architecture notes, or governance policies shared across modules.

This structure mirrors Minkowski’s approach by keeping frontends in `apps/`, backend/data work in `services/` or `infra/`, and shared knowledge in `docs/`, preventing the drift that results from ad-hoc “modules” and making it easy for contributors to find the right home for new work.


### Planned Agents
| Persona (at MH) | Agent Name | Agent / Tool                    | Description                                                                        | Domain          | Priority  |
| -------------- | ---------- | ------------------------------- | ---------------------------------------------------------------------------------- | --------------- | --------- |
| Bianca         | Ora        | Moodboard Generator             | Generates moodboards based on user defined aesthetics, products, style, theme etc. | Interior Design | Moderate  |
| Ryan           | Eko        | Social Media Handler            | Posts, engages, and manages the social media handle of the company                 | Generic         | Moderate  |
| Ethan          | Floc       | Content Creator (Ad/Email copies)| Generates marketing content based on brand kit and company knowledge              | Generic         | High      |
| Devin          | Cruz       | Manager's Assistant             |                                                                                    | Fast Food       | Very Low  |
| Emily          | Hosi       | Front of the House              |                                                                                    | Fast Food       | Very Low  |
| Tony           | Prex       | Back of the House               |                                                                                    | Fast Food       | Very Low  |
| Jaina          | Kall       | Phone Call/Customer Support Rep |                                                                                    | Generic         | High      |
| Sarah          | Leed       | Lead Generation Caller          |                                                                                    | Generic         | Immediate |
| Kim            | Kim        | Store Manager's Assistant       |                                                                                    | Generic         | Low       |
| Mark           | Insi       | Business Analyst                |                                                                                    | Generic         | Low       |
| Nathan         | Imel       | Email Handler                   |                                                                                    | Generic         | Immediate |

### Corporate website (apps/corporate-website)

1. `cd apps/corporate-website`  
2. Serve the folder with your favorite static server (for example `npm install --global http-server` followed by `http-server . -c-1`).  
3. Update the HTML, CSS, or assets to tell pluseleven’s story, then redeploy that folder to your CDN/hosting platform.  
4. Keep this site static so it can be deployed anywhere without additional compute. Currently hosted on Vercel at minkops.com
