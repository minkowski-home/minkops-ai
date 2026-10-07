"""Authenticated HTTP transport for the server-managed desktop companion."""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from minkops_platform import desktop
from minkops_platform.errors import ServiceError
from pydantic import BaseModel, ConfigDict, Field

from .auth import Db, User, require_csrf, tenant_access

router = APIRouter()


def call(action, *args):
    try:
        return action(*args)
    except ServiceError as error:
        status = {
            "invalid": 422,
            "not_found": 404,
            "conflict": 409,
            "forbidden": 403,
            "unauthorized": 401,
        }[error.kind]
        raise HTTPException(status, str(error)) from error


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    installation_id: UUID


class Launch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: UUID
    request_key: UUID
    operation: Literal["tally.probe", "files.refresh", "accounts.save", "tally.save"]
    input: dict = Field(default_factory=dict)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_token: UUID
    result: dict | None = None
    error: str | None = Field(default=None, min_length=1, max_length=300)


@router.get("/api/tenants/{slug}/desktop/devices")
def devices(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.devices, connection, tenant)


@router.post("/api/tenants/{slug}/desktop/devices", status_code=201)
def register(slug: str, body: Registration, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.register, connection, tenant, user, body.name, body.installation_id)


@router.delete("/api/tenants/{slug}/desktop/devices/{device_id}")
def revoke(slug: str, device_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.revoke, connection, tenant, user, device_id)


@router.post("/api/tenants/{slug}/desktop/jobs", status_code=202)
def launch(slug: str, body: Launch, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.launch, connection, tenant, user, body.model_dump(mode="json"))


@router.get("/api/tenants/{slug}/desktop/sources")
def sources(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.bindings, connection, tenant, user)


@router.post("/api/tenants/{slug}/desktop/devices/{device_id}/sources/{source_id}")
def bind_source(
    slug: str, device_id: UUID, source_id: UUID, request: Request, user: User, connection: Db
):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.bind_source, connection, tenant, user, device_id, source_id)


@router.get("/api/tenants/{slug}/desktop/jobs/{job_id}")
def detail(slug: str, job_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return call(desktop.job_detail, connection, tenant, user, job_id)


def worker_device(request: Request, connection: Db):
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 200:
        raise HTTPException(401, "Reconnect this PC from Minkops.")
    return call(desktop.authenticate, connection, authorization[7:])


Device = Annotated[dict, Depends(worker_device)]


@router.post("/api/desktop/worker/claim")
def claim(device: Device, connection: Db):
    return call(desktop.claim, connection, device)


@router.post(
    "/api/desktop/worker/jobs/{job_id}/finish",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": Receipt.model_json_schema()}},
        },
    },
)
async def finish(job_id: UUID, request: Request, device: Device, connection: Db):
    # Bound the wire payload before JSON allocation; base64 snapshots can be
    # larger than multipart uploads. The domain enforces decoded file limits.
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 42_000_000:
            raise HTTPException(413, "Choose a smaller folder: at most 30 MB of supported files.")
        chunks.append(chunk)
    try:
        body = Receipt.model_validate(json.loads(b"".join(chunks)))
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise HTTPException(422, "Invalid local task receipt.") from error
    return call(desktop.finish, connection, device, job_id, body.model_dump(mode="json"))


@router.get("/api/desktop/worker/jobs/{job_id}/plan")
def plan(job_id: UUID, claim_token: UUID, device: Device, connection: Db):
    return call(desktop.plan, connection, device, job_id, claim_token)
