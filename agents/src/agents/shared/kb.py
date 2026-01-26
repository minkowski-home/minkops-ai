'''
This module contains the agents' shared ability to access and modify the knowledge base outside of the database.
'''

import os
import typing
import logging
from typing import Sequence, Any

# Import sibling db module
from . import db

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 1536

class KBChunk(typing.TypedDict):
    content: str
    metadata: dict[str, Any]
    source_uri: str | None
    source_type: str | None

class TenantProfile(typing.TypedDict):
    brand_kit_text: str
    brand_kit: dict[str, Any]
    source_uri: str
    agent_display_name: typing.NotRequired[str]
    tone: typing.NotRequired[str]
    keywords: typing.NotRequired[str]
    email_signature: typing.NotRequired[str]

def _format_pgvector(values: Sequence[float]) -> str:
    """Format a Python sequence into a pgvector literal."""
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"

def _get_default_embedder():
    """Create a default embeddings client if configured."""
    try:
        from langchain_openai import OpenAIEmbeddings
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.debug("OpenAIEmbeddings unavailable: %s", exc)
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set; skipping KB vector lookup")
        return None

    return OpenAIEmbeddings(api_key=api_key)

def lookup_company_kb(
    *,
    tenant_id: str | None,
    query: str,
    top_k: int = 5,
    embedder=None,
    conn=None,
) -> list[KBChunk]:
    """Return KB chunks via pgvector similarity search, per tenant."""

    if not tenant_id:
        logger.info("Skipping KB lookup because tenant_id is missing")
        return []

    embedder = embedder or _get_default_embedder()
    if embedder is None:
        logger.info("No embedder configured; returning empty KB snippets for tenant %s", tenant_id)
        return []

    try:
        query_vector = embedder.embed_query(query)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to embed KB query for tenant %s: %s", tenant_id, exc)
        return []

    if len(query_vector) != EMBEDDING_DIMENSION:
        logger.debug(
            "KB embed dimension (%s) != expected (%s); proceeding anyway",
            len(query_vector),
            EMBEDDING_DIMENSION,
        )

    vector_literal = _format_pgvector(query_vector)

    close_conn = False
    if conn is None:
        conn = db.get_db_conn()
        close_conn = conn is not None

    if conn is None:
        logger.info("No DB connection available; returning empty KB snippets for tenant %s", tenant_id)
        return []

    rows: list[tuple[str, dict[str, Any], str | None, str | None]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata, source_uri, source_type
                FROM tenant_kb_chunks
                WHERE tenant_id = %s
                ORDER BY embedding <-> (%s)::vector
                LIMIT %s
                """,
                (tenant_id, vector_literal, top_k),
            )
            rows = cur.fetchall()
            
    # Defensive check for pgvector/table existence errors
    except Exception as exc:  
        logger.warning("KB lookup failed for tenant %s: %s", tenant_id, exc)
        return []
        
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass

    snippets: list[KBChunk] = []
    for content, metadata, source_uri, source_type in rows:
        metadata = metadata or {}
        snippet: KBChunk = {
            "content": content,
            "metadata": metadata,
            "source_uri": source_uri or metadata.get("source_uri"),
            "source_type": source_type or metadata.get("source_type"),
        }
        snippets.append(snippet)
    return snippets

def load_tenant_profile(*, tenant_id: str | None, conn=None) -> TenantProfile | None:
    """Load tenant branding/profile details from KB (brand_kit chunks)."""

    if not tenant_id:
        return None

    close_conn = False
    if conn is None:
        conn = db.get_db_conn()
        close_conn = conn is not None

    if conn is None:
        return None

    row: tuple[str, dict[str, Any], str | None] | None = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata, source_uri
                FROM tenant_kb_chunks
                WHERE tenant_id = %s
                  AND (source_type = 'brand_kit' OR metadata->>'kind' = 'brand_kit')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.info("No tenant profile found for %s: %s", tenant_id, exc)
        return None
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass

    if not row:
        return None

    content, metadata, source_uri = row
    metadata = metadata or {}
    profile: TenantProfile = {
        "brand_kit_text": content or "",
        "brand_kit": metadata.get("brand_kit", {}) if isinstance(metadata.get("brand_kit"), dict) else {},
        "source_uri": source_uri or metadata.get("source_uri", ""),
    }

    for key in ("agent_display_name", "tone", "keywords", "email_signature"):
        value = metadata.get(key)
        if value:
            profile[key] = value

    return profile