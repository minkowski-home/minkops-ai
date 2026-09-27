# PR Infra

This directory is the client composition boundary. Its manifest currently
declares the PR Infra identity and connector intent; it does not yet implement
the supplier-bill workflow.

As that workflow is built, place PR Infra-specific purchase-register mappings,
supplier rules, approval policy, and prompt overrides here. Keep generic
workflow execution and external-system clients outside this directory. The
shared console and API remain under `apps/`.
