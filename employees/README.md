# Employees and workflows

An employee is the customer-facing home for a set of business workflows. Add
an employee directory when there is an actual employee to offer.

Use `employees/<employee-id>/workflows/<workflow-id>/` for each workflow owned
by that employee. Keep its business goal, inputs, expected output, completion
checks, and evaluation examples together. Workflow instructions may guide an
Agents API session, but this directory is not a custom agent runtime.

Prefer the Agents API's managed Codex harness and available tools, web search,
skills, plugins, and MCP connections where they fit. Add custom code or a
plugin only for a specific gap. A skill is procedural guidance, not a
replacement for the workflow's business contract. Do not copy a tool
implementation into each employee.

Keep one canonical workflow owner. If several employees need the same business
workflow, extract its shared definition only when that reuse is real and have
the employee entries reference it. Customer-specific configuration belongs in
`solutions/<client-id>/employees/<employee-id>/`.

Example shape (illustrative paths, not implemented employees):

```text
employees/<employee-id>/
  README.md
  workflows/<workflow-id>/
    README.md
    evals/
```
