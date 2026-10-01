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

`minkops_connectors.excel` inspects workbooks and applies mapped row changes,
preserving unrelated cells and workbook structure. Application services supply
record validation; this adapter does not own tenant policy or workflow prompts.
