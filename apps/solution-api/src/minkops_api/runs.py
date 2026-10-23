"""HTTP binding for runs: small status, record pages, record detail and decisions.

Every route resolves the client business through per-client access first, and
reads only runs of that client and of the workflows the person runs. Workflow
rules live in the pinned handler.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from minkops_platform import clients, installation, members, work

from .accounts import _call
from .auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}/clients/{client}")


class Launch(BaseModel):
    workflow: str = Field(pattern="^[a-z][a-z0-9-]{0,60}$")
    file_ids: list[UUID] = Field(min_length=1, max_length=50)
    config: dict = Field(default_factory=dict)
    request_key: UUID


class Decision(BaseModel):
    action: str = Field(pattern="^[a-z][a-z_]{0,30}$")
    version: int = Field(ge=1)
    detail: dict = Field(default_factory=dict)


def scoped(connection, slug, client, user):
    tenant, member = tenant_access(slug, user, connection)
    return tenant, member, _call(clients.require, connection, tenant, user, member, client)


def run_of(connection, tenant, user, member, found, run_id):
    """A run of this client, of a workflow the person runs; any other run is indistinguishable from none."""
    run = _call(work.get_run, connection, tenant["id"], run_id)
    runs = members.assigned(connection, tenant, user, member)
    if run["client_id"] != found["id"] or (runs is not None and run["workflow_id"] not in runs):
        raise HTTPException(404, "Run not found.")
    return run


@router.post("/runs")
def launch(slug: str, client: str, body: Launch, request: Request, user: User, connection: Db):
    """Start a run of an installed workflow for this client; a repeated request key returns the same run."""
    require_csrf(request)
    tenant, member, found = scoped(connection, slug, client, user)
    _call(members.require_workflow, connection, tenant, user, member, key=body.workflow)
    workflow, definition = _call(installation.installed, connection, tenant["id"], body.workflow)
    handler = _call(work.handler_for, {"handler": workflow["execution_binding"]["handler"]})
    run = _call(lambda: handler.launch(connection, tenant=tenant, user=user, client=found, workflow=workflow,
                                       definition=definition, body=body.model_dump(mode="json")))
    return work.status(connection, tenant["id"], run["id"])


@router.post("/runs/{run_id}/approve")
def approve(slug: str, client: str, run_id: UUID, request: Request, user: User, connection: Db):
    """Write ready rows: approve every proposal of the run that needs no review."""
    require_csrf(request)
    tenant, member, found = scoped(connection, slug, client, user)
    run = run_of(connection, tenant, user, member, found, run_id)
    return _call(lambda: work.handler_for(run).approve_ready(connection, run, user["id"]))


@router.get("/runs/{run_id}/status")
def status(slug: str, client: str, run_id: UUID, user: User, connection: Db, since: str | None = None):
    tenant, member, found = scoped(connection, slug, client, user)
    run_of(connection, tenant, user, member, found, run_id)
    current = work.status(connection, tenant["id"], run_id)
    # A poll that already has this activity gets a tiny answer.
    return {"unchanged": True, "activity": current["activity"]} if since and since == current["activity"] else current


@router.get("/runs/{run_id}/records")
def records(slug: str, client: str, run_id: UUID, user: User, connection: Db,
            after: str | None = Query(default=None, pattern=r"^\d+:\d+$"), limit: int = Query(default=100, ge=1, le=200)):
    tenant, member, found = scoped(connection, slug, client, user)
    run = run_of(connection, tenant, user, member, found, run_id)
    handler = _call(work.handler_for, run)
    return work.records_page(connection, tenant["id"], run_id, after=after, limit=limit,
                             summarize=lambda record: handler.summarize(run, record))


@router.get("/records/{record_id}")
def record(slug: str, client: str, record_id: UUID, user: User, connection: Db):
    tenant, member, found = scoped(connection, slug, client, user)
    row = _call(work.get_record, connection, tenant["id"], record_id)
    run = run_of(connection, tenant, user, member, found, row["run_id"])
    return _call(work.handler_for, run).detail(connection, run, row)


@router.get("/records/{record_id}/ledgers")
def ledgers(slug: str, client: str, record_id: UUID, user: User, connection: Db,
            role: str = Query(pattern=r"^[a-z]{1,20}$"), q: str = Query(default="", max_length=100)):
    """The ledgers a reviewer may choose for one part of a record (`role`), from the books its run read."""
    tenant, member, found = scoped(connection, slug, client, user)
    row = _call(work.get_record, connection, tenant["id"], record_id)
    run = run_of(connection, tenant, user, member, found, row["run_id"])
    return _call(work.handler_for(run).ledgers, connection, run, row, role, q)


@router.post("/records/{record_id}/decisions")
def decide(slug: str, client: str, record_id: UUID, body: Decision, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member, found = scoped(connection, slug, client, user)
    row = _call(work.get_record, connection, tenant["id"], record_id)
    run = run_of(connection, tenant, user, member, found, row["run_id"])
    handler = _call(work.handler_for, run)
    context = {"user": user, "member": member, "tenant": tenant}
    return _call(lambda: work.decide(
        connection, tenant_id=tenant["id"], record_id=record_id, version=body.version, actor_id=user["id"],
        action=body.action, detail=body.detail,
        apply=lambda current: handler.decide(connection, run, current, body.action, body.detail, context)))
