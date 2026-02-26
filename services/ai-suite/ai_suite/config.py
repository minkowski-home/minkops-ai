"""Runtime configuration helpers.

We keep configuration parsing in the service layer because it is inherently
environment-dependent (local dev, CI, Docker, production).
"""

from __future__ import annotations

import dataclasses
import os
from dotenv import load_dotenv

load_dotenv(verbose=True)   # Remove in production: Should be handled by docker/K8s


@dataclasses.dataclass(frozen=True)
class Settings:
    """Typed runtime settings for the AI Suite orchestrator."""

    admin_db_url: str | None    # superuser — DDL operations only (seed-db)
    database_url: str | None    # app user  — runtime DML operations
    psql_path: str
    log_level: str


def load_settings() -> Settings:
    """Load runtime settings from environment variables.

    Environment variables:
    - `ADMIN_DB_URL`: Superuser Postgres URL used exclusively by `seed-db` for
      DDL operations (DROP/CREATE tables). Falls back to `DATABASE_URL` if unset,
      which preserves backwards compatibility for single-URL local setups.
    - `AGENTS_DB_URL` / `DATABASE_URL`: Least-privilege app user URL used by the
      runtime for all DML operations.
    - `PSQL_PATH`: Optional override for the `psql` binary location.
    - `LOG_LEVEL`: Python logging level (default: INFO).
    """

    database_url = os.getenv("AGENTS_DB_URL") or os.getenv("DATABASE_URL")
    admin_db_url = os.getenv("ADMIN_DB_URL") or database_url
    psql_path = os.getenv("PSQL_PATH") or "psql"
    log_level = os.getenv("LOG_LEVEL") or "INFO"
    return Settings(
        admin_db_url=admin_db_url,
        database_url=database_url,
        psql_path=psql_path,
        log_level=log_level,
    )

