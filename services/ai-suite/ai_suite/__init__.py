"""AI Suite service package.

`services/ai-suite` is the **agent runtime orchestrator** for this repository.
It executes agent graphs from the `agents/` library and owns all side effects:
database writes, outbox emission, inter-agent messaging, and external actions.

The `agents/` package remains a decisioning library (graphs/nodes/policies) plus
contracts (schemas and tool interfaces). It should not contain infrastructure
implementations.
"""

