# Database

`init/` remains a Docker Postgres bootstrap contract and is mounted directly by
`infra/compose.yml`. It is deliberately not called `migrations`: the scripts
currently create a fresh local database rather than apply incremental,
versioned changes. Introduce `migrations/` only together with a migration tool
and an upgrade path for existing deployments.
