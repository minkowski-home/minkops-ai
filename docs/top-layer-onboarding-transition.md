# Minkops Knowledge Transition: Top-Layer Engineering (Agents + Apps)

## 1) Purpose and audience

This document is for a new software engineer onboarding to this monorepo with primary responsibility for:

- building and extending agent logic in `agents/`
- building and evolving product surfaces in `apps/`

It gives a practical mental map of what exists today, what is production-like, what is scaffolded, and where top-layer work couples to runtime/data layers.

## 2) Monorepo mental map

Top-level folders and current status:

- `agents/`: Active core library of agent graphs/contracts (Python, LangGraph). You'll need to learn basics of langgraph, then understand how `Imel` is built, and then build other agents similarly. You'll be provided the high level graph, implementing it in Langgraph is your job.
- `apps/`: `corporate-website` is the active marketing app, and `client-app` is the scaffolded client facing application. Building the client app will be among your primary responsibilites. You might need to learn one of FastAPI (Python) or Node.js (Javascript).
- `services/ai-suite/`: Active runtime that executes agents and owns side effects. Not your primary responsibility, but knowing enough Python to understand how this communicates with `agents/` is important.
- `db/`: active operational DB bootstrap schema; warehouse/transform mostly scaffolded.
- `docs/`: Active decision log + brand guidelines + this onboarding doc. Any problems you encountered and were solved, or existing issues that you **solved**, should be documented here.
- `infra/`: placeholder (README exists, compose file currently empty). Dont worry about it.
- `transform/`: dbt starter scaffold only. Dont worry about it.

High-level architecture contract (important):

- Agents contain decision logic - they decide. E.g. they will recieve email text, and will decide what to reply, whether to reply, what part of database to change, etc.
- Runtime executes and persists. E.g. the decision made by agents, will be executed by this layer. `agents/` must never include code that touches databases.
- Apps expose/collect user interactions and marketing content. `corporate-website` is the traditional style website in FastAPI, it's a good practice ground for you to practice your app building skills before you can move to the more difficult `client-app`.
- DB owns durable state and cross-agent/event queues. You'll probably never need to touch it.

## 3) Tech stack snapshot

### Python/agent stack

- Python `3.12`
- LangGraph for graph orchestration. You'll start here with your first project.
- LangChain + `langchain-ollama`/`langchain-openai` for optional LLM use. Secrets will be shared through secrets manager.
- `psycopg2` for Postgres capability implementations. Knowing basics might be useful someday.
- `uv` lockfiles and project management in Python subprojects. Strong requirement that you understand uv from day 1.

### Web/app stack
(None of this should concern you except the backend part in the last bullet)
- React `18` + TypeScript + Vite
- Framer Motion for animations
- React Router for client routes
- CSS (custom, no utility framework)
- FastAPI minimal backends in `apps/*/api/backend`

### Data/infrastructure stack (planned vs current)

- Postgres operational schema implemented (`db/init_agents_db.sql`)
- pgvector supported with JSON fallback path
- dbt scaffold present but not yet modeled
- Docker/Terraform/K8s not yet implemented in repo

## 4) Current implementation maturity (what is real vs scaffold)

Implemented and usable:

- `agents/general/imel` (email triage + routing + ticket/handoff logic)
- `agents/general/kall` (ticket resolution flow)
Refining these two and making them shipping-ready withing 2 weeks will be immediate priorities.

- `services/ai-suite` CLI/runtime/adapters/capabilities
- `apps/corporate-website/frontend` full React site
- `apps/corporate-website/api/backend` health-check API
- `db/init_agents_db.sql` operational schema + seed tenant rows

Scaffold/placeholder:

- `agents/general/leed/*` empty files
- `apps/client-app/*` mostly empty starter
  (You'll take on these two next)

- `infra/docker-compose.yml` empty
- `db/schema/raw.sql`, `intermediate.sql`, `mart.sql` empty
- `transform/` is default dbt starter models
- `services/ai-suite/scripts/simulate_users.py` empty

## 5) Agents layer deep dive (`agents/`)

### 5.1 Design principle

`agents/` is intentionally a lightweight decisioning library, not a runtime service:

- no concrete DB/network side effects in agent modules
- tools are declared as `typing.Protocol` contracts (take a quick tutorial on the `Protocol` class in Python)
- runtime injects concrete implementations from `services/ai-suite`

This separation is the key engineering boundary for all new agent work.

### 5.2 Shared contracts (`agents/src/agents/shared`)

Core files:

- `schemas.py`: canonical shared `TypedDict` types (`Ticket`, `KBChunk`, `TenantProfile`)
- `db.py`: DB protocol contract + deprecated shims that raise runtime errors
- `kb.py`: KB protocol contract + deprecated shims that raise runtime errors
- `clients.py`: model factory (`ChatOllama`) used when runtime opts into LLM
- `utils.py`: helpers (`utc_now_iso`, JSON extraction)

Takeaway:

- if state/shape changes affect more than one agent, update `schemas.py` first
- avoid importing runtime-heavy dependencies into state/policy modules

### 5.3 Agent package pattern

Implemented agent directories use the same structure:

- `state.py`: Agent's state schema.
- `prompts.py`: Reusable prompt strings
- `policy.py`: Triple-layered policy/persona configuration
- `tools.py`: Runtime capability interface. Note that we define protocols here, none of this does the actual work. These are contracts, the actual work will be done by `services/` layer using these tools.
- `nodes.py`: pure state-transform nodes - that's where more of the decision making happens, and that's where most of your skills go.
- `graph.py`: LangGraph wiring + `run_<agent>()` entrypoint. This will be the orchestrated graph.

This is the canonical template for new agents.

### 5.4 Imel (`agents/general/imel`)

Role:
- inbound email triage + response drafting
- escalation to a human and handoff to another agent when needed

Flow:
1. Initialize run state.
2. Classify email intent (`classify_intent_node`).
3. Route by intent:
   - inquiry/general => KB lookup + draft response
   - order/account/update => enqueue order-update outbox + draft response
   - cancel/complaint or human-required => create ticket + handoff to Kall
   - spam => archive
4. Return final state/action.

Notable implementation details:

- fallback deterministic classification/drafting exists when no LLM is injected
- prompt layering supports tenant-specific brand profile overlay
- routing uses `langgraph.types.Command(goto=...)`

### 5.5 Kall (`agents/general/kall`)

Role:

- resolve escalated tickets and optionally send user update
- will later be used as a full swing support call handler

Flow:

1. Load ticket.
2. If missing: set `no_ticket`/respond fallback.
3. If found: close ticket, generate resolution message, send inter-agent completion handoff to Imel.

Implementation is intentionally deterministic/MVP-level.

### 5.6 Leed (`agents/general/leed`)

- scaffold only (all files currently empty)
- candidate for next top-layer implementation if lead-gen agent work is prioritized

### 5.7 How to add a new agent correctly

Minimum path:

1. Create `agents/src/agents/general/<agent_id>/` with the 6-file pattern above.
2. Keep `nodes.py` pure and side-effect free.
3. Define tool `Protocol` surface in `<agent>/tools.py`.
4. Add runtime adapter in `services/ai-suite/ai_suite/runtime/adapters.py`.
5. Add registry entry in `services/ai-suite/ai_suite/runtime/registry.py`.
6. Ensure DB/capability methods exist in `services/ai-suite/ai_suite/capabilities/postgres.py`.
7. Wire CLI convenience command only if needed (`run-<agent>` in CLI parser).

## 6) Runtime coupling you must understand (`services/ai-suite`)

Even as a top-layer engineer, these files define your integration contract.

Core runtime path:

- `ai_suite/cli.py`: `seed-db`, `run-agent`, `run-imel`, `run-kall`
- `ai_suite/runtime/registry.py`: maps `agent_id` to runner + adapter import paths
- `ai_suite/runtime/adapters.py`: payload validation, kwargs mapping, post-run side effects
- `ai_suite/runtime/runner.py`: generic run lifecycle (create run row, invoke graph, checkpoint, mark status)
- `ai_suite/capabilities/postgres.py`: concrete tool implementations for Imel/Kall

Why this matters:

- adding/changing agent tool calls in `agents/` usually requires matching runtime capability updates
- post-run user-visible effects (for now fake email send) are controlled by adapters, not agent nodes

## 7) Data model orientation (`db/init_agents_db.sql`)

Operational tables most relevant to top-layer behavior:

- `tenants`: organizations (our clients) isolation key
- `runs`: per-trigger run lifecycle - one agent run per row
- `agent_state`: checkpointed final state today (single checkpoint currently)
- `messages`: run message context
- `tickets`: support/escalation artifacts
- `event_outbox`: async side-effect queue - when an agent decides that some external side-effect needs to be done (like sending the email, or changing the database), that "task" is added to this table and the agent continues it's work. Then, some other worker (may be from `services/` will pick this task from this table, finish it and mark it done.
- `agent_intercom_queue`: inter-agent messages/handoffs - same as `event-outbox` but not for external side-effects, for giving control to other agent instead (for example, when email agent recieves a customer email that requires calling the customer, it will handoff control to the call agent)
- `human_instructions_queue`: async manager/agent instruction channel. Another queue-like table but this time for human employees of our clients adding tasks for agents (for example, a manager of the company logs in, then assigns 5 tasks to be done today, those will be added to this table from where agents can automatically pick their tasks)
- `tenant_kb_chunks`: tenant-scoped KB content (pgvector or JSON fallback) - knowledge base for our clients
- `activity_logs`: warehousing/sync-friendly activity stream

Important behavior:

- schema includes `CHECK` constraints on many status/type enums
- KB table creation has pgvector fallback path for lower-privilege local setups

## 8) Apps layer deep dive (`apps/`)
This will be your gold-mine. There will be various production-ready software engineering projects as we grow in the `apps/` layer. You might need to get a 4-5 hour tutorial of FastAPI (or Node.js if you prefer that) before beginning.  
### 8.1 `apps/corporate-website` (active)

### Frontend architecture (`frontend/`)

Entry:

- `src/main.tsx` bootstraps React app
- `src/App.tsx` central route map

Routes:

- `/` landing
- `/about`
- `/orchestration`
- `/blogs`
- `/blogs/minkowski-case-study`
- `/blogs/auto-lead-generation-agent`
- `/careers`
- `/terms`
- `/privacy`

Composition:

- shared shell/navigation/footer in `src/components/PageShell.tsx`, `SiteNav.tsx`, `SiteFooter.tsx`
- page-level components in `src/*.tsx`
- marketing interaction components:
  - `components/InterestForm.tsx` (currently local state + alert, no backend submission)
  - `components/AgentDemoSection.tsx` (animated showcase placeholder)

Styling system:

- `src/index.css`: global reset/font tokens
- `src/App.css`: global app/page component class system and design tokens
- page/component scoped CSS files:
  - `AboutPage.css`
  - `components/InterestForm.css`
  - `components/AgentDemoSection.css`

Tooling:

- Vite dev server on `5173`
- ESLint + TypeScript strict mode
- Prettier config included
- API proxy: `/api` => `VITE_API_TARGET` (default `http://127.0.0.1:5000`)

Legacy artifact:

- `frontend/public/legacy/` contains older static HTML/CSS/JS site branded as `pluseleven`
- this is not part of the active React routing path and can be ignored

### Backend (`api/backend`)

- FastAPI app with only `/health`
- CORS allows local frontend origins
- currently minimal placeholder for future marketing endpoints
- You'll take ownership of this and grow it - including developing a full backend, integrating with database, following engineering best practices.

### 8.2 `apps/client-app` (scaffold)

Current state:

- README empty
- backend `app/main.py` just prints "Hello from backend!"
- package skeleton exists but no meaningful API or frontend client code yet
- You'll take ownership of this and grow it - including developing a full backend, integrating with database, following engineering best practices.

## 9) Docs and decisions you should read first

Must-read files:

- `README.md` (repo intent + planned agents)
- `docs/decisions-log.md` (architectural rationale and recent major changes)
- `docs/brand-guidelines.md` (marketing style language. If ever tasked to work on frontend, you'll follow these)

Decision log highlights relevant to top-layer work:

- shared schema consolidation into `agents/shared/schemas.py`
- runtime centralization into `services/ai-suite`
- adapter-based generic runtime contract
- LangGraph standardization for Imel/Kall
- local bootstrap hardening for pgvector permission differences

## 10) Local development runbook (practical)

### 10.1 Corporate website frontend

From repo root run these commands in terminal:
```bash
cd apps/corporate-website/frontend
npm install
npm run dev
```

### 10.2 Corporate website backend

From repo root:
```
cd apps/corporate-website/api/backend
uv sync
uv run main.py
```

### 10.3 Agent runtime

From repo root:
- Setup local Postgres with a username and password on your Mac
- ensure Postgres is running and reachable by `DATABASE_URL` in secrets
```
cd services/ai-suite
uv sync
uv run main.py seed-db --tenant-id tenant_001 --kb-path data/tenant_001/company_kb/kb.md
uv run main.py run-imel --tenant-id tenant_001 --sender customer@example.com --email "I want to cancel my order"
```

Notes:

- `data/` is gitignored; seed defaults expect local files to exist.
- `seed-db` is destructive to DB `minkops_app`.

## 11) Learning path for a new top-layer engineer
Assumptions:
- You understand Python modules and packages, and functional paradigm.
- You understand basic concepts like `typing.Protocols`, `Pydantic`, `TypedDict`,and deep ones like object-oriented Python, SQL ORMs. Gemini is a way better teacher than ChatGPT at this stage.
- You understand Git and GitHub in depth.
- Do NOT read every line of code for the following one-week plan. You just need to understand what a particular module does, how it connects to another module, what every function does (what args it takes and what it returns), that's it. What's inside the function (every line of code, how it's implemented) is not super important right now.
- For any new terminology you encounter, you'll learn about it where it appears.
- After week 1, you will use Codex heavily - the goal is to ship at least one feature a day - either by solving it yourself (start each session that way), or by making Codex do it and then understanding how it did it (this solves the "where should i start" problem.)

Day 1-3:

- read `README.md` + `docs/decisions-log.md`
- Read [Langgraph Quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart), [Thinking in Langgraph](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph), and [Workflows vs agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents). We will always use the Graph API and not the Functional API. Create one tiny agent in rough space, may be a weather agent or email agent, just for practice.
- Read [Postgres Getting Started](https://www.postgresql.org/docs/current/tutorial-start.html), [The SQL Language](https://www.postgresql.org/docs/current/tutorial-sql.html), and [Postgres Advanced Topics](https://www.postgresql.org/docs/current/tutorial-advanced.html). This is hardly 4-5 hours of study - you must include practice questions on each big topic (ChatGPT can generate some for you).
- Read the `db/init_agents_db.sql`, understand all the tables, all the constraints, and reasoning behind decisions.
- trace one full Imel run:
  - `agents/general/imel/*` -> runtime adapter -> Postgres capability (You will not understand it completely, and that's not a problem.)

Day 3-6:

- Read the `services/` layer, and how it interacts with `agents/`. This is the most difficult, brainfuck, time-taking part; only do it when you have undivided 3-4 hours - this part requires compounding context and taking a break mid-task might need you to restart. Start top-down: 
  - By this point, you understand the `agents/` layer. Now, in `services/ai-suite/`, understand what `main.py`, `cli.py`, and `config.py` do.
  - Then, understand the tools - `capabilities/`. That's where we take actions decided by `agents/`.
  - Then, move to `runtime/`, understand what are `adapters.py` and what's `registry.py`, and how `runner.py` works with all the above components. Try to make a flowchart on rough notebook if that helps. 
- Inspect a run
  - Inspect the rows in `runs`, `agent_state`, `tickets`, `agent_intercom_queue`)
  - Find a way to improve Imel, and implement a small change in Imel prompts/policy and verify via CLI run
  - inspect DB rows created by one run (`runs`, `agent_state`, `tickets`, `agent_intercom_queue`) after the run

Week 1 target competency:

- add a new node or intent branch in Imel safely
- understand where runtime integration updates are required
- make end-to-end UI + backend wiring changes in `apps/corporate-website`

## 12) Known traps and mismatches

These are likely onboarding friction points:

- Many folders/files are placeholders; avoid assuming they are production-ready.
- No automated tests currently present for agent/app flows.
- `apps/corporate-website/api/backend/main.py` runs Uvicorn with `"src.main:app"` even though file path is `main.py`.
- `apps/corporate-website/api/backend/pyproject.toml` wheel target references `packages = ["src"]`, but there is no `src/` package layout.
- `services/ai-suite/playground.ipynb` contains ad hoc experimental content and embedded credentials-like strings; do not treat as production reference.
- Runtime currently saves one final checkpoint (`checkpoint_id=1`) instead of node-by-node durable checkpoints.

## 13) Recommended initial contribution opportunities

High-value top-layer improvements you can pick after the onboarding week:

- implement `Leed` agent skeleton using existing Imel/Kall conventions
- wire `InterestForm` to backend endpoint (and persistence/email capture path)
- clean backend packaging/entrypoint mismatches in `apps/corporate-website/api/backend`
- add baseline tests for:
  - Imel routing by intent
  - Kall ticket-not-found + resolved paths
  - corporate frontend route smoke checks
- add a concise runtime README under `services/ai-suite` for faster onboarding

## 14) Glossary (repo-specific language)

- Run: one atomic unit of triggered agent work.
- Agent state: in-memory run state checkpointed into `agent_state`.
- Adapter: runtime glue mapping generic payloads to agent-specific runner kwargs and post-run effects.
- Capability: concrete runtime-owned implementation of side effects (DB/email/etc.).
- Intercom queue: internal agent-to-agent messaging table.
- Outbox: durable queue for external side effects.

After week 1, we will provide a 4-5 month detailed SWE competency roadmap that will make you a top contributor to Minkops (or in general).
