"""HTTP binding for runs: small status, record pages, record detail and decisions.

Every route resolves the client business through per-client access first, and
reads only runs of that client. Workflow rules live in the pinned handler.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from minkops_platform import clients, work

from .accounts import _call
from .auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}/clients/{client}")


class Decision(BaseModel):
    action: str = Field(pattern="^[a-z][a-z_]{0,30}$")
    version: int = Field(ge=1)
    detail: dict = Field(default_factory=dict)


def scoped(connection, slug, client, user):
    tenant, member = tenant_access(slug, user, connection)
    return tenant, member, _call(clients.require, connection, tenant, user, member, client)


def run_of(connection, tenant, found, run_id):
    """A run of this client only; another client's run is indistinguishable from none."""
    run = _call(work.get_run, connection, tenant["id"], run_id)
    if run["client_id"] != found["id"]:
        raise HTTPException(404, "Run not found.")
    return run


@router.get("/runs/{run_id}/status")
def status(slug: str, client: str, run_id: UUID, user: User, connection: Db, since: str | None = None):
    tenant, _, found = scoped(connection, slug, client, user)
    run_of(connection, tenant, found, run_id)
    current = work.status(connection, tenant["id"], run_id)
    # A poll that already has this activity gets a tiny answer.
    return {"unchanged": True, "activity": current["activity"]} if since and since == current["activity"] else current


@router.get("/runs/{run_id}/records")
def records(slug: str, client: str, run_id: UUID, user: User, connection: Db,
            after: str | None = Query(default=None, pattern=r"^\d+:\d+$"), limit: int = Query(default=100, ge=1, le=200)):
    tenant, _, found = scoped(connection, slug, client, user)
    run = run_of(connection, tenant, found, run_id)
    handler = _call(work.handler_for, run)
    return work.records_page(connection, tenant["id"], run_id, after=after, limit=limit,
                             summarize=lambda record: handler.summarize(run, record))


@router.get("/records/{record_id}")
def record(slug: str, client: str, record_id: UUID, user: User, connection: Db):
    tenant, _, found = scoped(connection, slug, client, user)
    row = _call(work.get_record, connection, tenant["id"], record_id)
    run = run_of(connection, tenant, found, row["run_id"])
    return _call(work.handler_for, run).detail(connection, run, row)


@router.post("/records/{record_id}/decisions")
def decide(slug: str, client: str, record_id: UUID, body: Decision, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member, found = scoped(connection, slug, client, user)
    row = _call(work.get_record, connection, tenant["id"], record_id)
    run = run_of(connection, tenant, found, row["run_id"])
    handler = _call(work.handler_for, run)
    context = {"user": user, "member": member, "tenant": tenant}
    return _call(lambda: work.decide(
        connection, tenant_id=tenant["id"], record_id=record_id, version=body.version, actor_id=user["id"],
        action=body.action, detail=body.detail,
        apply=lambda current: handler.decide(connection, run, current, body.action, body.detail, context)))
