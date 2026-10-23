"""HTTP binding for the tenant's files: uploaded sources, their current files, and each file's content."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from minkops_api.auth import Db, User, require_csrf, tenant_access
from minkops_api.service import call as _call
from minkops_platform import files

router = APIRouter(prefix="/api/tenants/{slug}/accounts")


@router.get("/sources")
def sources(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return _call(files.list_sources, connection, tenant)


@router.post("/sources")
async def upload_source(
    slug: str,
    request: Request,
    user: User,
    connection: Db,
    uploads: Annotated[list[UploadFile], File(alias="files")],
    paths: Annotated[str, Form()],
    label: str = Form("Uploaded files"),
    writable: bool = Form(False),
    source_id: Annotated[UUID | None, Form()] = None,
    upload_id: Annotated[UUID | None, Form()] = None,
    final: bool = Form(True),
):
    """Upload files as a source; a set larger than one request arrives in batches of one upload (files.py)."""
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    try:
        names = json.loads(paths)
        if not isinstance(names, list) or len(names) != len(uploads) or not 1 <= len(uploads) <= files.MAX_FILES:
            raise ValueError(f"Choose between 1 and {files.MAX_FILES} files with their relative paths.")
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)) from error
    contents = [await upload.read(files.MAX_FILE_BYTES + 1) for upload in uploads]
    return _call(files.upload_source, connection, tenant, user, names, contents, label, writable, source_id,
                 upload_id=upload_id, final=final)


@router.get("/files/{file_id}/content")
def source_content(slug: str, file_id: UUID, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    content, media = _call(files.content, connection, tenant["id"], file_id)
    return Response(content, media_type=media)
