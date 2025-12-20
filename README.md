# MinkOps.ai

Minkops.ai is a suite of autonomous AI employees that handle customer intake, operational monitoring, administration, analytics, and communication through a unified knowledge graph, policy model, and orchestration layer. 

## Layout

- `apps/` — user-facing experiences; currently `apps/corporate-website` hosts the Minkops marketing site.
- `services/` — production and prototype services; `services/ai-suite` is the conversational/operational agent platform plus legacy notebooks and tooling.
- `infra/` — infrastructure plans and automation (currently contains a README placeholder but can grow Terraform, Kubernetes, or GH Actions artifacts).
- `docs/` — cross-cutting playbooks, architecture notes, or governance policies shared across modules.

This structure mirrors Minkowski’s approach by keeping frontends in `apps/`, backend/data work in `services/` or `infra/`, and shared knowledge in `docs/`, preventing the drift that results from ad-hoc “modules” and making it easy for contributors to find the right home for new work.

## Getting started

### AI suite (services/ai-suite)

1. `cd services/ai-suite`  
2. Create an environment: `python3 -m venv .venv && source .venv/bin/activate`.  
3. Install dependencies with either `pip install -r requirements.txt` for a slim sandbox or `conda create --name pluseleven --file all_legacy_code/requirements/requirements.txt` for the legacy stack.  
4. Study `all_legacy_code/` for the FastAPI/GUI agents and the notebooks that capture training workflows.  
5. When the orchestrator stack arrives, `infra/` will host the compose/Kubernetes manifests needed to bring the agents online.

### Corporate website (apps/corporate-website)

1. `cd apps/corporate-website`  
2. Serve the folder with your favorite static server (for example `npm install --global http-server` followed by `http-server . -c-1`).  
3. Update the HTML, CSS, or assets to tell pluseleven’s story, then redeploy that folder to your CDN/hosting platform.  
4. Keep this site static so it can be deployed anywhere without additional compute.

## Governance

- Treat each directory as a mini-module with its own README (like Minkowski’s `apps/` and `services/`).  
- Add new functionality under `apps/`, `services/`, or `infra/` depending on whether it is user-facing, service-level, or infrastructure-related.  
- Sync policies, onboarding, and architecture notes inside `docs/` so every contributor can see the same playbook.  
- Keep cross-cutting scripts and helper data in `packages/` (to be added later) or under `services/ai-suite/docs/` until we add a dedicated shared space.
