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

Current solutions under plan are:
- WhatsApp -> Excel data reconciliation
- RBI Account Aggregator/Finvu/OneMoney/etc based on transactions reconciliation (must not change client's existing tools, for example, if they use Excel to keep all transaction data currently, our job is to simply automate transactions and record into Excel, not replace Excel)

## Deployment TODO

`app.minkops.com` is the shared Minkops console, not a PR Infra-only domain.
Before production rollout, create or identify its Vercel project with
`apps/solution-web` as the root directory, apply the SPA rewrite in that app's
`vercel.json`, and attach/verify `app.minkops.com`. Tenant membership must choose
the solution after sign-in; until that backend exists, the host exposes explicit
solution paths such as `/pr-infra/dashboard`.
