"""Authenticated transport for shared attention; membership does not grant new PC resources."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from minkops_platform import attention, clients, members

from .accounts import _call
from .auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}/attention")


def scope(connection, tenant, user, member):
    """The clients this person reaches and the workflows they run (by key), as attention takes them."""
    runs = members.assigned(connection, tenant, user, member)
    return {"visible": clients.visible_ids(connection, tenant, user, member),
            "workflows": None if runs is None else list(runs.values())}


@router.get("")
def items(slug: str, user: User, connection: Db, status: Literal["pending", "done", "all"] = "pending",
          offset: int = Query(default=0, ge=0), group: Literal["workflow", "employee", "status", "client"] = "workflow",
          sort: Literal["newest", "name"] = "newest"):
    tenant, member = tenant_access(slug, user, connection)
    return _call(attention.listing, connection, tenant["id"], status=status, offset=offset, group=group, sort=sort,
                 **scope(connection, tenant, user, member))


@router.post("/{item_id}/done")
def mark_done(slug: str, item_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(attention.done, connection, tenant["id"], user, item_id, **scope(connection, tenant, user, member))


class Answer(BaseModel):
    # One of the answers the question offers; its own module checks which.
    action: str = Field(pattern="^[a-z][a-z_]{0,30}$")


@router.get("/{item_id}/decision")
def decision_receipt(slug: str, item_id: UUID, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    return _call(attention.decision_receipt, connection, tenant["id"], user["id"], item_id,
                 **scope(connection, tenant, user, member))


@router.post("/{item_id}/decision")
def decide(slug: str, item_id: UUID, body: Answer, request: Request, user: User, connection: Db):
    """Answer a question card, such as how to read a statement's dates."""
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(attention.decide, connection, tenant, user, item_id, body.action,
                 **scope(connection, tenant, user, member))
