# Solutions

A solution configures the shared Minkops product for one customer. Keep the
existing top-level `solution.ts` manifest for the current shared console.

`installation.json` selects an existing tenant and employee references; each
selected employee's `binding.json` declares workflows, initial defaults/status,
and trusted policies. The web build discovers solution manifests automatically.
See [workflow authoring](../docs/workflow-authoring.md) for validation,
installation, and the boundary between composition and resource authorization.

Put employee-specific customer composition under
`solutions/<client-id>/employees/<employee-id>/` when that employee is enabled
for the customer. This is the place for enabled workflow references,
customer-specific instructions and mappings, tool access, approval policy, and
output destinations. Reference the canonical workflow under `employees/`;
do not copy its implementation or create a customer-specific app.

The `solution.ts` manifest declares console identity and an optional tenant-slug
mapping. Tool selection belongs in `workflow-policy.json`; employee/workflow
selection belongs in the installation and bindings. These declarations do not
authorize resource access. Bind real tool access per customer and per session.
Keep secrets out of repository configuration, instructions, and plugin archives.

`mock-client` selects Source discovery, Bill entry and Statement entry for the
mock tenant. `pr-infra` selects Source discovery and Statement entry. Both reuse
Accounts desk definitions; actual execution and native saves require authorized
resources. See [the release verification](../docs/verification-accounts-release-20261019.md)
for deployed evidence and remaining client setup.
