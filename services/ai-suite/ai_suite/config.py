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

    database_url: str | None
    psql_path: str
    log_level: str


def load_settings() -> Settings:
    """Load runtime settings from environment variables.

    Environment variables:
    - `AGENTS_DB_URL` / `DATABASE_URL`: Postgres connection URL.
    - `PSQL_PATH`: Optional override for the `psql` binary location.
    - `LOG_LEVEL`: Python logging level (default: INFO).
    """

    database_url = os.getenv("AGENTS_DB_URL") or os.getenv("DATABASE_URL")
    psql_path = os.getenv("PSQL_PATH") or "psql"
    log_level = os.getenv("LOG_LEVEL") or "INFO"
    return Settings(database_url=database_url, psql_path=psql_path, log_level=log_level)

