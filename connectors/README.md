# Connectors

Use OpenAI-provided tools or an existing MCP integration when it can meet the
workflow's needs and customer access policy. Add code here only for an external
system Minkops must implement or mediate itself.

A connector owns protocol-specific access and data mapping. Expose narrow,
permissioned actions through MCP or application function tools as appropriate;
keep workflow instructions in `employees/` and customer selection and policy
in `solutions/`. Do not place credentials in employee or solution files.

The installable `minkops_connectors` package lives in `src/`. Add adapters
there as their concrete integrations are implemented.

`minkops_connectors.statement` reads bank statements (CSV, and XLSX through
`excel.open_workbook`), and `minkops_connectors.documents` renders bill pages for
sessions. Neither edits a file, and neither owns tenant policy or workflow prompts.
