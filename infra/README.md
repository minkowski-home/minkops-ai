# Infrastructure

This folder will hold Terraform, Docker Compose, Kubernetes overlays, and GitHub automation that deploys the AI suite and other apps. Infrastructure manifests should reference the same shared policies described elsewhere in the repo and expose environment-specific overlays (dev/stage/prod) similar to the `env/` directory from Minkowski’s layout.

### Current
The `docker-compose.yml` is for local/dev. It launches infra + one gateway/orchestrator:
- `ai-suite/` (FastAPI)
- Vector DBs
- Relational DBs
- Message Broker (optional)
- etc.

### For multiple orgs
This is handled inside the app. Each request carries `org_id`. Shared KB client always filters/uses `org_id`. Agent availability is config/DB rule, not a separate service.

#### Different orgs use different agent sets
- Keep a per-org config table `org_agents` (with keys like `org_id`, `agent_id`, `enabled`, `config_json`)
- The gateway checks `org_id` and only routes to enabled agents

#### Per-org Knowleddge Base
Per‑org KB is set up at org onboarding and then enforced on every ingest/query.

Minimal, practical setup:

Org signup creates a KB scope
Create an org record in SQL: org_id, name, kb_namespace, plan
Create a vector namespace/collection for that org
Example: kb_namespace = "org_<org_id>"
Ingestion always writes into that scope
Ingest pipeline takes org_id
It stores raw docs in object storage under orgs/<org_id>/...
It writes embeddings into the vector DB namespace for that org
Every chunk has metadata: {org_id, source, doc_type, doc_id}
Retrieval always reads from that scope
All queries require org_id
The KB client resolves org_id -> namespace
Query is run only against that namespace or with org_id filter
That’s the core. The “how” depends on which vector store you pick:

Option A: Single index, per‑org namespaces (common early)

Vector DB supports namespaces/collections
Namespace name = org_<org_id>
Query = namespace=org_<org_id>
Option B: One collection per org

Create a collection per org
Query hits only that collection
Option C: Separate DB per org (strong isolation)

Separate DB instance per org
Most costly; used for enterprise compliance