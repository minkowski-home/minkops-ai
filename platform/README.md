# Platform

Customer-independent infrastructure belongs here. The current AI decisioning
library and runtime are intentionally separated beneath `platform/ai/`:

- `agents/` contains decision graphs and side-effect-free contracts.
- `runtime/` executes graphs and owns persistence and external effects.

Future cross-solution capabilities such as auth, tenancy, audit, approvals,
files, jobs, and notifications should be added here when they become concrete.
