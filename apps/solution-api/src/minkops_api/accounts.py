"""HTTP binding for shared Accounts services; no workflow execution implementation."""

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from minkops_api.auth import Db, User, require_csrf, tenant_access
from minkops_platform.accounts import repository, service
from minkops_platform.errors import ServiceError

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
    schema_only: bool = Form(False),
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
        service.upload_source, connection, tenant, user, names, contents, label, writable, source_id,
        schema_only=schema_only,
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
        ".csv": "text/csv; charset=utf-8",
    }[Path(file["path"]).suffix.lower()]
    return Response(bytes(file["content"]), media_type=media)


class Launch(BaseModel):
    key: str = Field(pattern="^[a-z][a-z0-9-]*$", max_length=100)
    request_key: UUID
    file_ids: list[UUID] = Field(min_length=1, max_length=1000)
    catalog_id: UUID | None = None
    destination_device_id: UUID | None = None
    config: dict = Field(default_factory=dict)


class Review(BaseModel):
    result: dict
    acknowledge_findings: bool = False


@router.post("/runs", status_code=202)
def launch(slug: str, body: Launch, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    payload = body.model_dump(mode="json")
    if payload["destination_device_id"] is None:
        # Preserve pre-selector request hashes for retries across an upgrade.
        payload.pop("destination_device_id")
    return _call(service.launch_run, connection, tenant, user, payload)


@router.get("/runs/{run_id}")
def run_detail(slug: str, run_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(repository.public_run_for, connection, tenant["id"], run_id)


@router.get("/runs/{run_id}/unsaved-bills.csv")
def unsaved_bills(slug: str, run_id: UUID, user: User, connection: Db):
    from minkops_platform.accounts.bill_review import attention_items, export_csv

    tenant, _ = tenant_access(slug, user, connection)
    run = _call(repository.run_for, connection, tenant["id"], run_id)
    if run["workflow_key"] != "bill-entry":
        raise HTTPException(404, "Bill run not found.")
    content = _call(export_csv, run, attention_items(connection, run))
    return Response(content, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="unsaved-bills-{run_id}.csv"',
        "Cache-Control": "private, no-store",
    })


@router.get("/tasks/{task_id}/run")
def task_run(slug: str, task_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(repository.task_run, connection, tenant, task_id)


@router.get("/runs/{run_id}/statement-exceptions.csv")
def statement_exceptions(slug: str, run_id: UUID, user: User, connection: Db):
    from minkops_platform.accounts.statements import export_csv
    tenant, _ = tenant_access(slug, user, connection)
    run = _call(repository.run_for, connection, tenant["id"], run_id)
    if run["workflow_key"] != "statement-entry":
        raise HTTPException(404, "Statement run not found.")
    return Response(_call(export_csv, run), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="statement-exceptions-{run_id}.csv"',
        "Cache-Control": "private, no-store",
    })


@router.post("/runs/{run_id}/approve")
def approve(slug: str, run_id: UUID, body: Review, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    return _call(service.approve_run, connection, tenant, user, run_id, body.model_dump())
