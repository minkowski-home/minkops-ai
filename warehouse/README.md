# Warehouse

Not yet implemented. The approved design and step-by-step build plan, starting
with the OLTP corrections it depends on, is [docs/warehouse-plan.md](../docs/warehouse-plan.md).

The first implementation is a local PostgreSQL warehouse (`minkops_warehouse`)
loaded from the OLTP through `postgres_fdw` and transformed with dbt. Production
tooling (BigQuery, CDC, scheduling) follows the gates in that plan.
