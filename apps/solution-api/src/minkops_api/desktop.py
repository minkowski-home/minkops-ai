"""Authenticated HTTP transport for the server-managed desktop companion."""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from minkops_platform import desktop
from minkops_platform.accounts import sync
from minkops_platform.errors import ServiceError

from .auth import Db, User, database_pool, require_csrf, tenant_access

router = APIRouter()


def call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
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
    operation: Literal["tally.probe", "files.refresh"]
    input: dict = Field(default_factory=dict)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_token: UUID
    result: dict | None = None
    error: str | None = Field(default=None, min_length=1, max_length=300)
    # Bounded technical evidence for support; excluded from the receipt identity.
    diagnostic: dict | None = None


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


class DeviceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tally_port: int = Field(ge=1, le=65535)


@router.patch("/api/tenants/{slug}/desktop/devices/{device_id}")
def update_device(slug: str, device_id: UUID, body: DeviceSettings, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return call(sync.set_port, connection, tenant, user, member, device_id, body.tally_port)


@router.post("/api/tenants/{slug}/desktop/devices/{device_id}/sync", status_code=202)
def request_sync(slug: str, device_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return call(sync.request, connection, tenant, user, member, device_id)


@router.get("/api/tenants/{slug}/desktop/devices/{device_id}/companies")
def device_companies(slug: str, device_id: UUID, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    return call(sync.companies, connection, tenant, user, member, device_id)


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
    device = call(desktop.authenticate, connection, authorization[7:])
    # A short independent transaction prevents a streamed/slow receipt from
    # withholding presence while its authorization fence remains in force.
    with database_pool().connection() as pulse:
        call(desktop.touch_presence, pulse, device)
    return device


Device = Annotated[dict, Depends(worker_device)]


@router.post("/api/desktop/worker/heartbeat")
def heartbeat(device: Device):
    """Authentication records presence without claiming or extending any job.

    The answer carries the PC's Tally port, so the companion's own checks and
    diagnostics read the same Tally its jobs do.
    """
    return {"tally_port": device["tally_port"]}


class Installation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID


@router.post("/api/desktop/worker/installation")
def installation(body: Installation, device: Device, connection: Db):
    """Companion 0.11.2+: this PC's record takes the installation ID derived from its machine and Windows user."""
    return call(desktop.adopt_installation, connection, device, body.installation_id)


@router.post("/api/desktop/worker/claim")
def claim(
    device: Device,
    connection: Db,
    version: Annotated[str | None, Header(alias="X-Minkops-Companion-Version", max_length=20)] = None,
    host: Annotated[str | None, Header(alias="X-Minkops-Host", max_length=200)] = None,
    session: Annotated[str | None, Header(alias="X-Minkops-Session", max_length=20)] = None,
):
    # Every poll reports the PC's companion; older releases report nothing.
    return call(desktop.claim, connection, device, desktop.companion_report(version, host, session))


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
    # Bound the wire payload before JSON allocation: a folder refresh carries
    # its files in base64. The domain enforces decoded file limits.
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 48_000_000:
            raise HTTPException(413, "This receipt exceeds the supported transfer size.")
        chunks.append(chunk)
    try:
        body = Receipt.model_validate(json.loads(b"".join(chunks)))
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise HTTPException(422, "Invalid local task receipt.") from error
    return await run_in_threadpool(call, desktop.finish, connection, device, job_id, body.model_dump(mode="json"))


@router.post("/api/desktop/worker/diagnostics", status_code=201)
async def diagnostics(request: Request, device: Device, connection: Db):
    body = await request.body()
    if len(body) > 80_000:
        raise HTTPException(413, "Diagnostics are too large.")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(422, "Invalid diagnostics.") from error
    return call(desktop.send_diagnostics, connection, device, payload)


@router.post("/api/desktop/worker/jobs/{job_id}/sync")
async def sync_page(job_id: UUID, request: Request, device: Device, connection: Db):
    """One bounded page of a running sync; resending the same page is safe."""
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 12_000_000:
            raise HTTPException(413, "A sync page is limited to 12 MB.")
        chunks.append(chunk)
    try:
        page = json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(422, "Invalid sync page.") from error
    if not isinstance(page, dict):
        raise HTTPException(422, "Invalid sync page.")
    return await run_in_threadpool(call, desktop.sync_page, connection, device, job_id, page)


@router.get("/api/desktop/worker/jobs/{job_id}/plan")
def plan(job_id: UUID, claim_token: UUID, device: Device, connection: Db,
         plan_version: Annotated[int, Header(alias="X-Minkops-Plan-Version", ge=1, le=100)] = 1):
    return call(desktop.plan, connection, device, job_id, claim_token, plan_version)
