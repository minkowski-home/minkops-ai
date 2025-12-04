# pluseleven AI Suite

pluseleven AI Suite is the organization’s flagship AI product: a collection of conversational, operational, administrative, analytical, and communications agents that behave as autonomous employees. All agents share a unified knowledge graph, honor organization policies, plug into a central orchestration layer with audit trails and failover safeguards, and expose APIs for easy integration with existing inventory, payroll, CRM, and communication systems.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Directory Structure](#directory-structure)
- [Development Setup](#development-setup)
- [Testing](#testing)
- [License](#license)

---
## Overview

The AI Suite converges legacy kiosk automation code, model training notebooks, and orchestration scripts into a single, extensible module. Core capabilities include multimodal intake, personalized upselling, voice-identity monitoring, and telemetry surfaces for staffing, inventory, and compliance. The code in `all_legacy_code/` illustrates real-world agent pipelines, while `docs/` captures the emerging knowledge graph, policy model, and orchestrator contracts.

## Architecture

```
[Customers & Edge Devices]
          │
          ▼
[FastAPI Gateway & GUI Agents]──▶[Unified Knowledge Graph + Policy Layer]
          │
          ▼                      ▲
[LangChain Orchestrator] ──▶[Audit & Failover Layer]
          │
          ▼
[Data Stores (MySQL, Vector DBs, Redis/MQTT)]
          │
          ▼
[External APIs / Systems]
```

The orchestrator harmonizes the agents, pushes state updates into the knowledge graph, emits audit-ready events, and reroutes traffic to backup services when necessary. Vector search and PyTorch-based models provide real-time personalization, while multimedia ingestion and operational scripts keep inventory and attendance in sync.

---
## Tech Stack

**Edge & GUI**

- Windows IoT / WPF for kiosk interaction and voice capture
- FastAPI transports frames, messages, and commands to the orchestrator

**Orchestration & AI**

- LangChain for agent workflows and retrieval-augmented generation
- PyTorch + Hugging Face Transformers for embeddings and avatars
- FAISS-style vector databases (planned) and MySQL for structured state
- Redis / MQTT for low-latency telemetry broadcasting

**Data & Integration**

- Analytics-driven dashboards rely on MySQL snapshots and event logs
- Policy enforcement is baked into the knowledge graph and orchestrator hooks
- Auditability and failover are surfaced via orchestrator middleware

---
## Directory Structure

- `docs/` — living architecture, API contracts, and model cards
- `all_legacy_code/src/` — prototype gateways, audio helpers, and face/voice utilities
- `all_legacy_code/notebooks/` — training and experimentation stories
- `all_legacy_code/resources/` — artifacts such as saved models and data snippets
- `scripts/` — tooling that stitches simulations or integration points
- `requirements.txt` — placeholder for lightweight environments (future); the canonical Conda requirements live at `all_legacy_code/requirements/requirements.txt`

---
## Development Setup

1. `cd services/ai-suite`
2. Create and activate an environment: `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies with either `pip install -r requirements.txt` for a minimal sandbox or `conda create --name pluseleven --file all_legacy_code/requirements/requirements.txt` to mirror the legacy agent environment.
4. Explore `all_legacy_code/docs/` for workflow guidance, and run the Python scripts under `all_legacy_code/src/` to test conversational flows. Many of the notebooks expect the same environment, so launch them via `jupyter lab all_legacy_code/notebooks` when needed.
5. When the orchestrator stack is ready, bring up the containers or Kubernetes manifests that publish the agents through a single API gateway. (The container manifests will live under `infra/` once that module is added.)

---
## Testing

Current validation is manual: execute the relevant notebooks under `all_legacy_code/notebooks/`, replay audio via `all_legacy_code/src/audio_mgmt.py`, or run `scripts/simulate_users.py` once its payload is defined. Add automated tests to `tests/` as the module matures.

---
## License

This project is licensed under the MIT License.
