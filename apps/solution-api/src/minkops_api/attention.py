"""Authenticated transport for shared attention; membership does not grant new PC resources."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
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
    action: Literal["nothing", "guess", "supplier", "retry"]


@router.post("/bills/{run_id}/{file_id}")
def bill_decision(slug: str, run_id: UUID, file_id: UUID, body: Decision, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(decide, connection, tenant, user, run_id, str(file_id), body.action)
