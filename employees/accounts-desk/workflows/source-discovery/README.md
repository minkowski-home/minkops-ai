# Source discovery

This shared workflow executes through Accounts desk's OpenAI-hosted Agents API
adapter. The model is `gpt-6-luna`. Client business schemas are discovered and
confirmed; they are not encoded in this workflow's source.

`workflow.json` references editable tenant defaults, run configuration,
instructions and `agent-output.schema.json`. The latter validates hosted agent
proposals before review. `output.schema.json` remains the separate final-report
contract supported by the platform validator; it is not the agent proposal.

Source discovery proposes actual workbook/sheet/table mappings with header
positions and semantic concepts. Bill entry recognizes the appropriate confirmed
destination, extracts PDFs/images, supplies field evidence and reports unresolved
routing. The application owns approvals, checks and verified in-place Excel
writes. Registered-PC discovery collects all loaded Tally companies' complete,
undated masters and detailed vouchers for an inclusive date period, plus fresh
workbook projections containing headers, tables and formula text. Excel business
rows and cached results stay out of discovery. Hosted interpretation proposes
evidenced obscure Tally conventions and provisional Excel mappings for review.
The tenant owns its immutable version 2 package; new Tally bill runs pin its full
lookup evidence and company GUIDs without collecting references themselves.
Native imports still recheck current company and master identities. Legacy
schema-only catalogs remain readable but cannot launch new Tally bill runs.

See [Accounts desk](../../../../docs/accounts-desk.md) for setup, ownership,
recovery and supported workbook limits.

`execution-instructions.md` contains the hosted agent turn instructions, loaded
by the shared Accounts execution binding alongside this workflow's `SKILL.md`.
