"""Authenticated transport for shared attention; membership does not grant new PC resources."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, Field
from minkops_platform import attention
from minkops_platform.accounts.attention import decide
from .auth import Db, User, require_csrf, tenant_access
from .accounts import _call

router = APIRouter(prefix="/api/tenants/{slug}/attention")


@router.get("")
def items(slug: str, user: User, connection: Db, status: Literal["pending", "done", "all"] = "pending",
          offset: int = Query(default=0, ge=0), group: Literal["workflow", "employee", "status"] = "workflow",
          sort: Literal["newest", "name"] = "newest"):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(attention.listing, connection, tenant["id"], status=status, offset=offset, group=group, sort=sort)


@router.post("/refresh")
def refresh_all(slug: str, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(attention.refresh, connection, tenant["id"], user)


@router.post("/{item_id}/done")
def mark_done(slug: str, item_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(attention.done, connection, tenant["id"], user, item_id)


@router.post("/{item_id}/refresh")
def refresh_one(slug: str, item_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(attention.refresh, connection, tenant["id"], user, item_id)


class Decision(BaseModel):
    action: Literal["nothing", "guess", "supplier", "retry", "retry_save"]
    # Index of the bill in the run result; a file can hold several bills.
    proposal: int | None = Field(default=None, ge=0)


class BulkDecision(Decision):
    preview_token: str = Field(pattern="^[0-9a-f]{64}$")


@router.post("/bills/{run_id}/{file_id}/bulk-preview")
def bulk_preview(slug: str, run_id: UUID, file_id: UUID, body: Decision, request: Request, user: User, connection: Db):
    from minkops_platform.accounts.bulk_decisions import preview
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(preview, connection, tenant, user, run_id, str(file_id), body.action, body.proposal)


@router.post("/bills/{run_id}/{file_id}/bulk")
def bulk_apply(slug: str, run_id: UUID, file_id: UUID, body: BulkDecision, request: Request, user: User, connection: Db):
    from minkops_platform.accounts.bulk_decisions import apply
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(apply, connection, tenant, user, run_id, str(file_id), body.action, body.proposal, body.preview_token)


@router.post("/bills/{run_id}/{file_id}")
def bill_decision(slug: str, run_id: UUID, file_id: UUID, body: Decision, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(decide, connection, tenant, user, run_id, str(file_id), body.action, body.proposal)
