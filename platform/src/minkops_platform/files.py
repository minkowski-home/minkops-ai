"""Files a tenant gives Minkops: uploaded in the browser, or a PC's connected folder refreshed by its companion.

A source is one upload or one connected folder. Refreshing a source replaces
which of its files are current, and runs read only current files. Every file
must open as what its name claims before it is stored, so a run never meets
a mislabelled or empty file. Sources grant no access to anything else.
"""

import hashlib
from pathlib import Path, PurePosixPath

from minkops_connectors.excel import open_workbook

from .errors import ServiceError

# How each file begins; a workbook must also open, and a CSV is checked when a run reads it.
SIGNATURES = {".pdf": (b"%PDF-",), ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",),
              ".jpeg": (b"\xff\xd8\xff",), ".webp": (b"RIFF",)}
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         ".csv": "text/csv; charset=utf-8"}
MAX_FILES, MAX_FILE_BYTES, MAX_SOURCE_BYTES = 100, 5_000_000, 30_000_000


def safe_path(path):
    """A relative path inside its source: no absolute, parent, empty or backslash parts."""
    if (not isinstance(path, str) or not PurePosixPath(path).parts or path.startswith("/") or "\x00" in path
            or "\\" in path or any(part in ("", ".", "..") for part in path.split("/"))):
        raise ValueError("Choose a relative file path inside the selected source.")
    if len(path) > 500:
        raise ValueError("File path is too long.")
    return path


def _check(name, content):
    suffix = Path(name).suffix.lower()
    if suffix not in MEDIA:
        raise ValueError("Only PDF, PNG, JPEG, WebP, XLSX and CSV files are supported.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Each file must be nonempty and at most 5 MB.")
    if suffix == ".xlsx":
        open_workbook(content)
    elif not content.startswith(SIGNATURES.get(suffix, (b"",))) or (suffix == ".webp" and content[8:12] != b"WEBP"):
        raise ValueError("The selected PDF is invalid." if suffix == ".pdf" else "The selected image is invalid.")


def upload_source(connection, tenant, user, names, contents, label, writable, source_id=None):
    """Store a source's files as its current set; `source_id` refreshes an existing source.

    `writable` marks a PC's connected folder, which only its owner refreshes.
    """
    try:
        if not isinstance(names, list) or len(names) != len(contents) or not 1 <= len(contents) <= MAX_FILES:
            raise ValueError(f"Choose between 1 and {MAX_FILES} files with their relative paths.")
        names = [safe_path(name) for name in names]
        if len(names) != len(set(names)):
            raise ValueError("Source paths must be unique.")
        if not label.strip() or len(label) > 120:
            raise ValueError("Source label must contain 1–120 characters.")
        for name, content in zip(names, contents, strict=True):
            _check(name, content)
        if sum(map(len, contents)) > MAX_SOURCE_BYTES:
            raise ValueError("A source refresh is limited to 30 MB.")
    except (ValueError, TypeError, KeyError) as error:
        raise ServiceError("invalid", str(error)) from error
    if source_id:
        source = connection.execute("SELECT * FROM account_sources WHERE tenant_id=%s AND id=%s FOR UPDATE",
                                    (tenant["id"], source_id)).fetchone()
        if not source:
            raise ServiceError("not_found", "Source not found.")
        if source["actor_id"] != user["id"] and not user["is_platform_admin"]:
            raise ServiceError("forbidden", "Only the source owner can refresh this local folder.")
        if source["writable"] != writable:
            raise ServiceError("invalid", "A source cannot change its write capability.")
    else:
        source = connection.execute(
            "INSERT INTO account_sources (tenant_id,actor_id,label,writable) VALUES (%s,%s,%s,%s) RETURNING *",
            (tenant["id"], user["id"], label, writable)).fetchone()
    connection.execute("UPDATE account_files SET current=false WHERE tenant_id=%s AND source_id=%s AND current",
                       (tenant["id"], source["id"]))
    saved = [connection.execute(
        """INSERT INTO account_files (tenant_id,source_id,path,sha256,content) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (tenant_id,source_id,path,sha256) DO UPDATE SET current=true RETURNING id,path,sha256""",
        (tenant["id"], source["id"], path, hashlib.sha256(content).hexdigest(), content)).fetchone()
        for path, content in zip(names, contents, strict=True)]
    return {"id": source["id"], "label": source["label"], "writable": writable, "files": saved}


def list_sources(connection, tenant):
    """Every source of the tenant with its current files, oldest first."""
    rows = connection.execute("SELECT id,label,writable FROM account_sources WHERE tenant_id=%s ORDER BY created_at",
                              (tenant["id"],)).fetchall()
    for row in rows:
        row["files"] = connection.execute(
            "SELECT id,path,sha256 FROM account_files WHERE tenant_id=%s AND source_id=%s AND current ORDER BY path",
            (tenant["id"], row["id"])).fetchall()
    return rows


def files_for(connection, tenant_id, ids):
    """These files of the tenant, each with its source; any outside the tenant is not found."""
    rows = connection.execute(
        """SELECT f.*, s.writable, s.label FROM account_files f JOIN account_sources s
           ON s.tenant_id=f.tenant_id AND s.id=f.source_id
           WHERE f.tenant_id=%s AND f.id=ANY(%s::uuid[])""",
        (tenant_id, ids),
    ).fetchall()
    if len(rows) != len(set(ids)):
        raise ServiceError("not_found", "One or more files are not in this workspace.")
    return rows


def content(connection, tenant_id, file_id):
    """A file's bytes and media type, for viewing it beside its record."""
    file = files_for(connection, tenant_id, [str(file_id)])[0]
    return bytes(file["content"]), MEDIA[Path(file["path"]).suffix.lower()]
