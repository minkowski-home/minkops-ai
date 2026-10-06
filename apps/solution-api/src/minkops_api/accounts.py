"""HTTP binding for shared Accounts services; no workflow execution implementation."""

import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from minkops_platform.accounts import repository, service
from minkops_platform.accounts.repository import public_run
from minkops_platform.accounts.service import prepare_writes as prepare_writes
from minkops_platform.errors import ServiceError
from pydantic import BaseModel, Field

from minkops_api.auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}/accounts")


def _call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ServiceError as error:
        status = {"invalid": 422, "not_found": 404, "forbidden": 403, "conflict": 409}[error.kind]
        raise HTTPException(status, str(error)) from error


@router.get("/sources")
def sources(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(repository.list_sources, connection, tenant)


@router.get("/catalogs")
def catalogs(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(repository.list_catalogs, connection, tenant)


@router.get("/runs")
def runs(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(repository.list_runs, connection, tenant)


@router.post("/sources")
async def upload_source(
    slug: str,
    request: Request,
    user: User,
    connection: Db,
    files: Annotated[list[UploadFile], File()],
    paths: Annotated[str, Form()],
    label: str = Form("Uploaded files"),
    writable: bool = Form(False),
    source_id: Annotated[UUID | None, Form()] = None,
):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    try:
        names = json.loads(paths)
        if not isinstance(names, list) or len(names) != len(files) or not 1 <= len(files) <= 100:
            raise ValueError("Choose between 1 and 100 files with their relative paths.")
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)) from error
    contents = [await file.read(5_000_001) for file in files]
    return _call(
        service.upload_source, connection, tenant, user, names, contents, label, writable, source_id
    )


@router.get("/files/{file_id}/content")
def source_content(slug: str, file_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    file = _call(repository.files_for, connection, tenant["id"], [str(file_id)])[0]
    media = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[Path(file["path"]).suffix.lower()]
    return Response(bytes(file["content"]), media_type=media)


class Launch(BaseModel):
    key: Literal["source-discovery", "bill-entry"]
    request_key: UUID
    file_ids: list[UUID] = Field(min_length=1, max_length=45)
    catalog_id: UUID | None = None
    config: dict = Field(default_factory=dict)


class Review(BaseModel):
    result: dict
    acknowledge_findings: bool = False


class BillInput(BaseModel):
    file_id: UUID
    user_input: str = Field(default="", max_length=2000)
    reject: bool = False


@router.post("/runs/{run_id}/resolve-bill")
def resolve_bill(
    slug: str, run_id: UUID, body: BillInput, request: Request, user: User, connection: Db
):
    from minkops_platform.accounts.batch import resolve_bill as resolve

    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(
        resolve, connection, tenant, user, run_id, str(body.file_id), body.user_input, body.reject
    )


@router.post("/runs", status_code=202)
def launch(slug: str, body: Launch, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(service.launch_run, connection, tenant, user, body.model_dump(mode="json"))


@router.get("/runs/{run_id}")
def run_detail(slug: str, run_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return public_run(connection, _call(repository.run_for, connection, tenant["id"], run_id))


@router.get("/tasks/{task_id}/run")
def task_run(slug: str, task_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(repository.task_run, connection, tenant, task_id)


@router.post("/runs/{run_id}/approve")
def approve(slug: str, run_id: UUID, body: Review, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(service.approve_run, connection, tenant, user, run_id, body.model_dump())


@router.get("/runs/{run_id}/writes/{write_id}/content")
def write_content(slug: str, run_id: UUID, write_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    content = _call(service.write_content, connection, tenant, run_id, write_id)
    return Response(
        content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.post("/runs/{run_id}/writes/{write_id}/verify")
async def verify_write(
    slug: str,
    run_id: UUID,
    write_id: UUID,
    request: Request,
    user: User,
    connection: Db,
    file: Annotated[UploadFile, File()],
):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    content = await file.read(5_000_001)
    return _call(service.verify_write, connection, tenant, run_id, write_id, content)


@router.post("/runs/{run_id}/cancel-writes")
def cancel_writes(slug: str, run_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(service.cancel_writes, connection, tenant, run_id)
