"""HTTP binding for client businesses, per-client access and company authorisation."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from minkops_platform import clients
from minkops_platform.accounts import sync

from .accounts import _call
from .auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}")


class NewClient(BaseModel):
    slug: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=120)


class Access(BaseModel):
    user_id: UUID


class Authorise(BaseModel):
    client: str = Field(min_length=1, max_length=63)


@router.get("/clients")
def listing(slug: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    return _call(clients.listing, connection, tenant, user, member)


@router.post("/clients", status_code=201)
def create(slug: str, body: NewClient, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(clients.create, connection, tenant, user, member, body.slug, body.name)


@router.post("/clients/{client}/access")
def grant(slug: str, client: str, body: Access, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(clients.grant, connection, tenant, user, member, client, body.user_id)


@router.delete("/clients/{client}/access/{user_id}")
def revoke(slug: str, client: str, user_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(clients.revoke, connection, tenant, user, member, client, user_id)


@router.get("/clients/{client}/companies")
def companies(slug: str, client: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    found = _call(clients.require, connection, tenant, user, member, client)
    return [{key: row[key] for key in ("id", "name", "guid", "books_from", "company_number", "device_id",
                                       "device_name", "last_seen_at")}
            for row in clients.companies(connection, tenant, found)]


@router.post("/companies/{company_id}/authorise")
def authorise(slug: str, company_id: UUID, body: Authorise, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    # Authorising also closes the company's card and queues its first full sync. For the client that holds the
    # same books on a disconnected PC, it continues that company here.
    return _call(sync.authorise, connection, tenant, user, member, company_id, body.client)


@router.post("/companies/{company_id}/decline")
def decline(slug: str, company_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(sync.decline, connection, tenant, user, member, company_id)
