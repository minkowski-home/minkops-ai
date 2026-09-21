# PR Infra

This solution starts clean. Add only PR Infra-specific work here:

- `schemas/` for its extracted-record contract
- `prompts/` for customer-specific extraction instructions
- `rules/` for validation and approval policy
- `mappings/` for its Excel column mapping
- `workflows/` for its composition of reusable modules and connectors

The shared starter workspace is supplied by `apps/solution-web`; only add a
bespoke `web/` implementation when PR Infra needs to replace part or all of it.
Reusable extraction, review, and connector code belongs in `modules/`,
`platform/`, and `connectors/` respectively.
