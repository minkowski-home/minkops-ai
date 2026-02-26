"""Dev database seeding.

This module intentionally shells out to `psql` to apply `db/schema.sql`
because that file contains `psql`-specific meta-commands and is designed
to be executed exactly as-is (similar to how Docker init scripts run).

Prerequisites: `db/bootstrap.sql` must have been run once as a superuser to
create the `minkops_app` database, install extensions, and configure the
`minkops` role. `seed_database()` assumes the database already exists and
connects directly to it.
"""

from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import typing
import psycopg2

logger = logging.getLogger(__name__)


def _read_text(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def _resolve_path(path: str) -> pathlib.Path:
    """Resolve a path from CWD first, then monorepo root.

    The CLI is often executed from `services/ai-suite`, while defaults like
    `db/schema.sql` and `data/...` are rooted at the repo top level.
    """

    candidate = pathlib.Path(path)
    if candidate.exists():
        return candidate
    if candidate.is_absolute():
        return candidate

    repo_root = pathlib.Path(__file__).resolve().parents[4]
    repo_candidate = repo_root / candidate
    if repo_candidate.exists():
        return repo_candidate
    return candidate


def _placeholder_vector(dims: int = 1536) -> str:
    """Return a pgvector literal for a zero-vector of the desired dimension.

    In a real app this should be produced by an ingestion pipeline that chunks
    and embeds content using a configured embeddings model.
    """

    return "[" + ",".join(["0"] * dims) + "]"


def _placeholder_vector_json(dims: int = 1536) -> str:
    """Return a JSON array string for fallback embedding storage.

    This is used when pgvector is not enabled and `tenant_kb_chunks` uses the
    `embedding_json` column in local development.
    """

    return json.dumps([0] * dims)


def seed_database(
    *,
    sql_path: str,
    tenant_id: str,
    kb_markdown_path: str,
    admin_db_url: str | None,
    database_url: str | None,
    psql_path: str = "psql",
) -> None:
    """Reset the dev DB schema and seed a tenant + brand kit KB chunk.

    `admin_db_url` (superuser / gauss) is used for the psql DDL pass — dropping
    and recreating tables requires table ownership. `database_url` (app user /
    minkops) is used for the subsequent psycopg2 seeding inserts.
    """

    if not admin_db_url:
        raise RuntimeError("ADMIN_DB_URL is required for seeding (DDL operations require superuser access).")
    if not database_url:
        raise RuntimeError("DATABASE_URL/AGENTS_DB_URL is required for seeding.")

    sql_file = _resolve_path(sql_path)
    if not sql_file.exists():
        raise FileNotFoundError(f"Seed SQL file not found: {sql_path}")

    logger.warning("About to DROP and recreate all tables in `minkops_app`. This is destructive.")

    cmd = [psql_path, admin_db_url, "-v", "ON_ERROR_STOP=1", "-f", str(sql_file)]
    logger.info("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "psql binary not found. Install Postgres client tools (psql) or run seeding via Docker init scripts. "
            "You can also set PSQL_PATH to an absolute psql path."
        ) from exc

    # After DB is created, connect to it and upsert tenant + KB content.
    kb_path = _resolve_path(kb_markdown_path)
    if not kb_path.exists():
        raise FileNotFoundError(f"KB markdown file not found: {kb_markdown_path}")
    kb_markdown = _read_text(str(kb_path))

    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            # The bootstrap SQL can create either a pgvector column (`embedding`)
            # or a JSON fallback (`embedding_json`) depending on DB privileges.
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'tenant_kb_chunks'
                      AND column_name = 'embedding'
                )
                """
            )
            has_vector_column = bool(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO tenants (id, name, config, enabled)
                VALUES (%s, %s, '{}'::jsonb, TRUE)
                ON CONFLICT (id) DO UPDATE SET enabled=EXCLUDED.enabled
                """,
                (tenant_id, "Tenant 001"),
            )

            if has_vector_column:
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
                        str(kb_path),
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
            else:
                logger.warning(
                    "pgvector column not found in tenant_kb_chunks; using JSON embedding fallback for local dev."
                )
                cur.execute(
                    """
                    INSERT INTO tenant_kb_chunks
                      (tenant_id, doc_id, source_uri, source_type, chunk_index, content, embedding_json, metadata)
                    VALUES
                      (%s, %s, %s, 'brand_kit', 0, %s, %s::jsonb, %s::jsonb)
                    """,
                    (
                        tenant_id,
                        "kb_md",
                        str(kb_path),
                        kb_markdown,
                        _placeholder_vector_json(),
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

    logger.info("Seed complete for tenant_id=%s using %s", tenant_id, str(kb_path))
