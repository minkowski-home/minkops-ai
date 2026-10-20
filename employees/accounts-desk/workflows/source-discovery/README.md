# Source discovery

Collects the client's context from the registered PC: all configured Tally
companies' complete masters and detailed vouchers for an inclusive period, plus
workbook projections with headers, tables and formula text (no Excel business
rows or cached values). A hosted interpretation then proposes evidenced, obscure
conventions and provisional Excel mappings for review; the run's AI context
toggle can skip it. Confirmation creates the tenant's immutable version 2
package that Bill entry and Statement entry pin.

- `workflow.json` declares the handler (`accounts.discovery`), configuration and
  the hosted execution bundle (`gpt-6-luna`), including
  `collection-config.schema.json` and `context-note.schema.json`.
- `SKILL.md` and `execution-instructions.md` guide the interpretation turn;
  `agent-output.schema.json` validates its proposal. `output.schema.json` is the
  descriptor's generic result contract; Accounts does not validate against it.

Native imports still recheck current company and master identities. Legacy
schema-only catalogs remain readable but cannot launch new Tally bill runs. See
[Source discovery](../../../../docs/source-discovery.md) for collection,
review and catalog contracts.
