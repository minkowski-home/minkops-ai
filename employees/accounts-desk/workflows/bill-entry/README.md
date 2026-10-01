# Bill entry

One general workflow for bill extraction, available-reference reconciliation,
review, and output. Version 0.2.0 supports PDF inputs and draft Excel outputs;
there is no separate bill-reconciliation definition.

Tenant preferences select review and output modes. Each run selects approved
source/file IDs, a catalog version, a confirmed business schema ID/version, a
destination, and reference checks. Field names, types, required values, and
destination mappings come from discovery and confirmation. Never claim a
PO/receipt match without corresponding records.

Completion requires validated bill records, page evidence, findings, required
review decisions, and a verified Excel artifact. Unresolved findings remain
visible. `output.schema.json` defines only the envelope: schema references,
records with business `data`, evidence, findings, review state, and artifacts.
It does not prescribe invoice fields or Excel columns. Business data is validated
separately against the confirmed schema snapshot pinned to the run. The catalog
can define summaries, line items, or client-specific fields as needed.

`validate_output` checks both layers and rejects schema/version mismatches.
Schema lookup, confirmation, catalog persistence, semantic mappings for selected
checks, and actual Excel layout are implemented with source discovery. If no
confirmed schema exists, bill entry cannot resolve a valid execution contract.
Mock schema IDs are examples only, not evidence that discovery has run.

The run/output schemas define the contract, not executable adapters. Agent
sessions, arithmetic tools, output generation, review enforcement, and durable
run storage are implemented in later stages.
