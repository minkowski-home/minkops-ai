# PR Infra

This is the PR Infra client composition boundary. Its `solution.ts` currently
declares identity and connector intent for the shared console. It does not
implement a supplier-bill workflow or grant an agent access to WhatsApp or
Excel.

When an employee and workflow are agreed, add their shared definition under
`employees/<employee-id>/workflows/<workflow-id>/`. Put PR Infra's enabled
workflow references, purchase-register mapping, supplier rules, approval
policy, and any customer instructions under `employees/<employee-id>/` here.
Keep shared workflow definitions, runtime services, and external-system clients
outside this solution directory.
