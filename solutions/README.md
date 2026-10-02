# Solutions

A solution configures the shared Minkops product for one customer. Keep the
existing top-level `solution.ts` manifest for the current shared console.

Put employee-specific customer composition under
`solutions/<client-id>/employees/<employee-id>/` when that employee is enabled
for the customer. This is the place for enabled workflow references,
customer-specific instructions and mappings, tool access, approval policy, and
output destinations. Reference the canonical workflow under `employees/`;
do not copy its implementation or create a customer-specific app.

Connector declarations in the current solution manifests are intent for the
console, not proof that a connector is implemented or authorized for an agent
session. Bind real tool access per customer and per session. Keep secrets out
of repository configuration, instructions, and plugin archives.

`mock-client` supplies the local mock-tenant composition, whose Source discovery
and Bill entry workflows use OpenAI-hosted Agents API execution. `pr-infra` is
the first client solution and has no implemented Agents API employee workflow.
Local mock-client execution does not imply a production deployment.
