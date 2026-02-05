"""Dev database seeding.

This module intentionally shells out to `psql` to apply `db/init_agents_db.sql`
because that file contains `psql`-specific meta-commands (`\\c`) and is designed
to be executed exactly as-is (similar to how Docker init scripts run).
"""

from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import typing
import urllib.parse

import psycopg2

logger = logging.getLogger(__name__)


def _admin_url(database_url: str) -> str:
    """Derive a maintenance DB URL for `DROP/CREATE DATABASE` operations.

    `db/init_agents_db.sql` drops/creates `minkops_app` and then `\\c` into it.
    To avoid being connected to the DB we're about to drop, we connect to the
    server's maintenance database (typically `postgres`).
    """

    parsed = urllib.parse.urlparse(database_url)
    if not parsed.path or parsed.path == "/":
        return database_url
    return urllib.parse.urlunparse(parsed._replace(path="/postgres"))


def _read_text(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def _placeholder_vector(dims: int = 1536) -> str:
    """Return a pgvector literal for a zero-vector of the desired dimension.

    In a real app this should be produced by an ingestion pipeline that chunks
    and embeds content using a configured embeddings model.
    """

    return "[" + ",".join(["0"] * dims) + "]"


def seed_database(
    *,
    sql_path: str,
    tenant_id: str,
    kb_markdown_path: str,
    database_url: str | None,
    psql_path: str = "psql",
) -> None:
    """Reset the dev DB and seed a tenant + brand kit KB chunk."""

    if not database_url:
        raise RuntimeError("DATABASE_URL/AGENTS_DB_URL is required for seeding.")

    sql_file = pathlib.Path(sql_path)
    if not sql_file.exists():
        raise FileNotFoundError(f"Seed SQL file not found: {sql_path}")

    logger.warning("About to DROP and recreate database `minkops_app`. This is destructive.")

    admin_url = _admin_url(database_url)
    cmd = [psql_path, admin_url, "-v", "ON_ERROR_STOP=1", "-f", str(sql_file)]
    logger.info("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "psql binary not found. Install Postgres client tools (psql) or run seeding via Docker init scripts. "
            "You can also set PSQL_PATH to an absolute psql path."
        ) from exc

    # After DB is created, connect to it and upsert tenant + KB content.
    kb_markdown = _read_text(kb_markdown_path)

    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenants (id, name, config, enabled)
                VALUES (%s, %s, '{}'::jsonb, TRUE)
                ON CONFLICT (id) DO UPDATE SET enabled=EXCLUDED.enabled
                """,
                (tenant_id, "Tenant 001"),
            )

            cur.execute(
                """
                INSERT INTO tenant_kb_chunks
                  (tenant_id, doc_id, source_uri, source_type, chunk_index, content, embedding, metadata)
                VALUES
                  (%s, %s, %s, 'brand_kit', 0, %s, (%s)::vector, %s::jsonb)
                """,
                (
                    tenant_id,
                    "kb_md",
                    kb_markdown_path,
                    kb_markdown,
                    _placeholder_vector(),
                    json.dumps(
                        {
                            "kind": "brand_kit",
                            "agent_display_name": "MH Concierge",
                            "tone": "senior designer, vibe-first luxury",
                            "keywords": ["vibe-first", "luxury", "modularity", "Minkowski", "MH"],
                            "email_signature": "— MH (Minkowski) Concierge",
                            "brand_kit": {"brand_name": "MH / Minkowski"},
                        }
                    ),
                ),
            )
    finally:
        conn.close()

    logger.info("Seed complete for tenant_id=%s using %s", tenant_id, kb_markdown_path)
