"""Postgres-backed capability implementations.

This module contains the operational code that talks to Postgres. It is owned
by the runtime (`services/ai-suite`) rather than `agents/` so that:

- Agents remain importable and testable without Postgres drivers or a live DB.
- DB transaction/idempotency semantics have a single owner (the runtime).
"""

from __future__ import annotations

import json
import logging
import typing
import uuid

import psycopg2

from agents.general.imel import tools as imel_tools
from agents.general.kall import tools as kall_tools
from agents.shared.schemas import KBChunk, TenantProfile, Ticket, TicketStatus, TicketType

logger = logging.getLogger(__name__)


def _normalize_brand_kit(value: object) -> dict[str, str]:
    """Normalize brand kit metadata into string values (defensive for authoring)."""

    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, raw in value.items():
        if not key:
            continue
        try:
            normalized[str(key)] = str(raw) if raw is not None else ""
        except Exception:
            continue
    return {k: v for k, v in normalized.items() if k and v}


def _normalize_keywords(value: object) -> list[str] | None:
    """Normalize keywords metadata into a list of non-empty strings."""

    if value is None:
        return None
    if isinstance(value, list):
        keywords = [str(v).strip() for v in value if v is not None]
        keywords = [k for k in keywords if k]
        return keywords or None
    if isinstance(value, str):
        keywords = [part.strip() for part in value.split(",")]
        keywords = [k for k in keywords if k]
        return keywords or None
    return None


class _RunsRepo:
    """Minimal repository for `runs` lifecycle management."""

    def __init__(self, parent: "PostgresCapabilities"):
        self._parent = parent

    def create_run(self, *, run_id: str, tenant_id: str, agent_id: str, input_payload: dict[str, typing.Any]) -> None:
        conn = self._parent._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs (id, tenant_id, agent_id, status, input_payload)
                    VALUES (%s, %s, %s, 'running', %s)
                    """,
                    (run_id, tenant_id, agent_id, json.dumps(input_payload)),
                )
        finally:
            conn.close()

    def mark_completed(self, *, run_id: str) -> None:
        conn = self._parent._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET status='completed', updated_at=NOW() WHERE id=%s",
                    (run_id,),
                )
        finally:
            conn.close()

    def mark_failed(self, *, run_id: str) -> None:
        """Mark a run as failed.

        We keep this minimal (no error column yet). In production, attach a
        structured error payload for observability and replay tooling.
        """

        conn = self._parent._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET status='failed', updated_at=NOW() WHERE id=%s",
                    (run_id,),
                )
        finally:
            conn.close()


class _StateRepo:
    """Minimal checkpoint store writing to `agent_state`."""

    def __init__(self, parent: "PostgresCapabilities"):
        self._parent = parent

    def save_checkpoint(self, *, run_id: str, checkpoint_id: int, node_name: str, state_data: dict[str, typing.Any]) -> None:
        conn = self._parent._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_state (run_id, checkpoint_id, state_data, node_name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (run_id)
                    DO UPDATE SET checkpoint_id=EXCLUDED.checkpoint_id, state_data=EXCLUDED.state_data, node_name=EXCLUDED.node_name
                    """,
                    (run_id, checkpoint_id, json.dumps(state_data), node_name),
                )
        finally:
            conn.close()


class PostgresCapabilities:
    """Capability bundle backed by Postgres.

    This is a single owner for Postgres connectivity. Individual capability
    "surfaces" (runs, state store, tickets, kb, outbox, intercom) are exposed
    via methods and small repos so they can be composed per-agent.
    """

    def __init__(self, *, database_url: str):
        self._database_url = database_url
        self.runs = _RunsRepo(self)
        self.state = _StateRepo(self)

    def _conn(self):
        """Create a new connection.

        For production you would use pooling and a unit-of-work abstraction.
        For this refactor we keep it simple and explicit.
        """

        return psycopg2.connect(self._database_url)

    def _create_agent_handoff(
        self,
        *,
        tenant_id: str,
        run_id: str | None,
        from_agent_id: str,
        to_agent_id: str,
        kind: str = "handoff",
        message: str | None = None,
        payload: dict[str, typing.Any] | None = None,
    ) -> None:
        """Queue an inter-agent message/handoff in the shared intercom table."""

        conn = self._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_intercom_queue
                    (tenant_id, run_id, from_agent_id, to_agent_id, kind, message, payload, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued')
                    """,
                    (
                        tenant_id,
                        run_id,
                        from_agent_id,
                        to_agent_id,
                        kind,
                        message or "",
                        json.dumps(payload or {}),
                    ),
                )
        except Exception as exc:
            logger.error("Failed to queue handoff: %s", exc)
            raise
        finally:
            conn.close()

    def _get_ticket(self, *, ticket_id: str, tenant_id: str) -> Ticket | None:
        """Load a ticket row and map DB status to the agent-facing `Ticket` schema."""

        conn = self._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, ticket_type, status, email_id, sender_email, summary, raw_email
                    FROM tickets
                    WHERE id = %s AND tenant_id = %s
                    LIMIT 1
                    """,
                    (ticket_id, tenant_id),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        db_status = str(row[2] or "").lower()
        # The database supports intermediate statuses; agent-facing schema keeps a smaller contract.
        mapped_status: TicketStatus = "closed" if db_status in {"closed", "resolved"} else "open"
        return {
            "ticket_id": str(row[0]),
            "ticket_type": typing.cast(TicketType, str(row[1])),
            "status": mapped_status,
            "email_id": str(row[3] or ""),
            "sender_email": str(row[4] or ""),
            "summary": str(row[5] or ""),
            "raw_email": str(row[6] or ""),
        }

    def _update_ticket_status(self, *, ticket_id: str, tenant_id: str, status: TicketStatus) -> None:
        """Persist a ticket status transition.

        Agent-facing `closed` maps to DB status `closed`; `open` maps to `open`.
        """

        conn = self._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tickets
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s AND tenant_id = %s
                    """,
                    (status, ticket_id, tenant_id),
                )
        finally:
            conn.close()

    # --- Imel tool implementation (implements the agent contract) ---
    def imel_tools(self) -> imel_tools.ImelTools:
        """Return an object implementing `agents.general.imel.tools.ImelTools`."""

        parent = self

        class _ImelToolsImpl:
            """Concrete Imel tool implementation backed by Postgres.

            This inner class keeps the tool surface co-located with its owning
            capability bundle while remaining private and easy to swap later.
            """

            def load_tenant_profile(self, *, tenant_id: str | None) -> TenantProfile | None:
                if not tenant_id:
                    return None
                conn = parent._conn()
                try:
                    with conn, conn.cursor() as cur:
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
                    logger.info("Tenant profile lookup failed for %s: %s", tenant_id, exc)
                    return None
                finally:
                    conn.close()

                if not row:
                    return None

                content, metadata, source_uri = row
                metadata = metadata or {}
                profile: TenantProfile = {
                    "brand_kit_text": content or "",
                    "brand_kit": _normalize_brand_kit(metadata.get("brand_kit")),
                    "source_uri": str(source_uri or metadata.get("source_uri", "") or ""),
                }

                agent_display_name = metadata.get("agent_display_name")
                if isinstance(agent_display_name, str) and agent_display_name.strip():
                    profile["agent_display_name"] = agent_display_name.strip()

                tone = metadata.get("tone")
                if isinstance(tone, str) and tone.strip():
                    profile["tone"] = tone.strip()

                email_signature = metadata.get("email_signature")
                if isinstance(email_signature, str) and email_signature.strip():
                    profile["email_signature"] = email_signature.strip()

                keywords = _normalize_keywords(metadata.get("keywords"))
                if keywords:
                    profile["keywords"] = keywords

                return profile

            def lookup_company_kb(self, *, tenant_id: str | None, query: str, top_k: int = 5) -> list[KBChunk]:
                # Placeholder implementation: without real embeddings, similarity search is not meaningful.
                # We return the most recent chunks so inquiries still get some context in dev.
                if not tenant_id:
                    return []
                conn = parent._conn()
                try:
                    with conn, conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT content, metadata, source_uri, source_type
                            FROM tenant_kb_chunks
                            WHERE tenant_id = %s
                            ORDER BY updated_at DESC
                            LIMIT %s
                            """,
                            (tenant_id, top_k),
                        )
                        rows = cur.fetchall()
                except Exception as exc:
                    logger.info("KB lookup failed for %s: %s", tenant_id, exc)
                    return []
                finally:
                    conn.close()

                snippets: list[KBChunk] = []
                for content, metadata, source_uri, source_type in rows:
                    metadata = metadata or {}
                    snippets.append(
                        {
                            "content": content,
                            "metadata": metadata,
                            "source_uri": source_uri or metadata.get("source_uri"),
                            "source_type": source_type or metadata.get("source_type"),
                        }
                    )
                return snippets

            def create_ticket(
                self,
                *,
                ticket_type: TicketType,
                email_id: str,
                sender_email: str,
                summary: str,
                raw_email: str,
                tenant_id: str,
            ) -> Ticket:
                conn = parent._conn()
                ticket_id = str(uuid.uuid4())
                try:
                    with conn, conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO tickets (id, tenant_id, email_id, ticket_type, status, sender_email, summary, raw_email)
                            VALUES (%s, %s, %s, %s, 'open', %s, %s, %s)
                            RETURNING id
                            """,
                            (ticket_id, tenant_id, email_id, ticket_type, sender_email, summary, raw_email),
                        )
                        row = cur.fetchone()
                        if row:
                            ticket_id = str(row[0])
                except Exception as exc:
                    logger.error("Failed to insert ticket: %s", exc)
                    raise
                finally:
                    conn.close()
                return {
                    "ticket_id": ticket_id,
                    "ticket_type": ticket_type,
                    "status": "open",
                    "email_id": email_id,
                    "sender_email": sender_email,
                    "summary": summary,
                    "raw_email": raw_email,
                }

            def create_agent_handoff(
                self,
                *,
                tenant_id: str,
                run_id: str | None,
                from_agent_id: str,
                to_agent_id: str,
                kind: str = "handoff",
                message: str | None = None,
                payload: dict[str, typing.Any] | None = None,
            ) -> None:
                parent._create_agent_handoff(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    from_agent_id=from_agent_id,
                    to_agent_id=to_agent_id,
                    kind=kind,
                    message=message,
                    payload=payload,
                )

            def process_order_update(
                self,
                *,
                tenant_id: str,
                email_id: str,
                summary: str,
                details: dict[str, typing.Any],
            ) -> None:
                conn = parent._conn()
                payload = {"email_id": email_id, "summary": summary, "details": details}
                try:
                    with conn, conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO event_outbox (tenant_id, event_type, payload, status)
                            VALUES (%s, 'update_order', %s, 'queued')
                            """,
                            (tenant_id, json.dumps(payload)),
                        )
                except Exception as exc:
                    logger.error("Failed to write outbox event: %s", exc)
                    raise
                finally:
                    conn.close()

        return typing.cast(imel_tools.ImelTools, _ImelToolsImpl())

    # --- Kall tool implementation (implements the agent contract) ---
    def kall_tools(self) -> kall_tools.KallTools:
        """Return an object implementing `agents.general.kall.tools.KallTools`."""

        parent = self

        class _KallToolsImpl:
            """Concrete Kall tool implementation backed by Postgres."""

            def get_ticket(self, *, ticket_id: str, tenant_id: str) -> Ticket | None:
                return parent._get_ticket(ticket_id=ticket_id, tenant_id=tenant_id)

            def update_ticket_status(self, *, ticket_id: str, tenant_id: str, status: TicketStatus) -> None:
                parent._update_ticket_status(ticket_id=ticket_id, tenant_id=tenant_id, status=status)

            def create_agent_handoff(
                self,
                *,
                tenant_id: str,
                run_id: str | None,
                from_agent_id: str,
                to_agent_id: str,
                kind: str = "message",
                message: str | None = None,
                payload: dict[str, typing.Any] | None = None,
            ) -> None:
                parent._create_agent_handoff(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    from_agent_id=from_agent_id,
                    to_agent_id=to_agent_id,
                    kind=kind,
                    message=message,
                    payload=payload,
                )

        return typing.cast(kall_tools.KallTools, _KallToolsImpl())
