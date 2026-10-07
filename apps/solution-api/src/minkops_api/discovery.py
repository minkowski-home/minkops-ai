"""Authenticated transport for client source discovery and JSON downloads."""

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response
from minkops_platform import desktop, discovery
from pydantic import BaseModel, ConfigDict

from .auth import Db, User, require_csrf, tenant_access
from .desktop import Device, call

router = APIRouter()


class Launch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: UUID
    request_key: UUID
    config: dict


class Confirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    excel_mappings: dict | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_token: UUID
    source_key: str
    status: Literal["reading", "ready", "unavailable"]
    category: str | None = None


@router.post("/api/tenants/{slug}/discovery/runs", status_code=202)
def launch(slug: str, body: Launch, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return call(discovery.launch, connection, tenant, user, body.model_dump(mode="json"))


@router.get("/api/tenants/{slug}/discovery/tasks/{task_id}")
def task(slug: str, task_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    row = connection.execute(
        "SELECT * FROM discovery_runs WHERE tenant_id=%s AND task_id=%s", (tenant["id"], task_id)
    ).fetchone()
    return discovery.detail(connection, row) if row else None


@router.get("/api/tenants/{slug}/discovery/latest")
def latest(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    row = connection.execute(
        "SELECT * FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s ORDER BY created_at DESC LIMIT 1",
        (tenant["id"], user["id"]),
    ).fetchone()
    return discovery.detail(connection, row) if row else None


@router.get("/api/tenants/{slug}/discovery/runs/{run_id}")
def detail(slug: str, run_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return discovery.detail(connection, call(discovery.get_run, connection, tenant["id"], run_id))


@router.post("/api/tenants/{slug}/discovery/runs/{run_id}/confirm")
def confirm(slug: str, run_id: UUID, body: Confirm, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return call(discovery.confirm, connection, tenant, user, run_id, body.model_dump())


@router.get("/api/tenants/{slug}/discovery/runs/{run_id}/catalog.json")
def download(slug: str, run_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    row = call(discovery.get_run, connection, tenant["id"], run_id)
    catalog = discovery.detail(connection, row)["catalog"]
    return Response(
        json.dumps(catalog, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="minkops-sources-{run_id}.json"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/api/desktop/worker/jobs/{job_id}/progress")
def progress(job_id: UUID, body: Observation, device: Device, connection: Db):
    job = call(desktop._claimed_job, connection, device, job_id, body.claim_token)
    if job["state"] != "executing" or job["operation"] != "sources.discover":
        from fastapi import HTTPException

        raise HTTPException(409, "Discovery is not collecting sources.")
    return call(discovery.progress, connection, device, job, body.model_dump(mode="json"))
