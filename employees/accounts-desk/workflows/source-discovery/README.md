# Source discovery

One general workflow for discovering approved business sources. Version 0.1.0
starts with Excel workbooks inside approved directory scopes. Other source
types require supported adapters before they can be selected.

`workflow.json` references tenant preferences, per-run configuration, result
schemas, and agent instructions. Tenant defaults select discovery depth and
file limits; each run selects sources, relative scope, exclusions, and refresh
mode. Limits apply across the run. Relative paths resolve under authorized
source roots; the future adapter must also enforce symlink and file boundaries.

Completion requires a persisted, versioned catalog with source provenance,
technical schemas, reference records when requested, and clearly separated
confirmed/proposed mappings. Report partial scans and unresolved meanings.
Output schema describes the catalog summary; catalog storage is a later stage.
