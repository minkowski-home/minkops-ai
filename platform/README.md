# Platform

Shared, customer-independent runtime infrastructure belongs here. Add a
component when more than one application or workflow needs it; keep workflow
specific business logic with the workflow until reuse justifies extraction.

AI Employees are product catalog entries that group workflows. A workflow owns
the business process and calls concrete tools or connectors. Keep reusable
procedural model guidance beside its first workflow; extract a skill only when
another workflow needs it. Add an agent only for a real autonomous reasoning
loop inside a workflow.
