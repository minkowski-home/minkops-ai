# Minkops warehouse

This dbt project owns analytical models and warehouse-specific dependencies.
It lives at the repository root as a distinct data subsystem. The local
compose configuration mounts it at `/opt/dbt` for Airflow jobs.
