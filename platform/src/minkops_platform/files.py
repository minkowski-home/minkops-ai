"""Files a tenant gives Minkops: uploaded in the browser, or a PC's connected folder refreshed by its companion.

A source is one upload or one connected folder. Refreshing a source replaces
which of its files are current, and runs read only current files. Every file
must open as what its name claims before it is stored, so a run never meets
a mislabelled or empty file. Sources grant no access to anything else.

An upload larger than one request arrives in batches (`account_uploads`): each
batch is staged, and the final one checks the whole set and makes it current at
once, so an abandoned upload leaves nothing current. Each request stays within
MAX_REQUEST_BYTES, which the API's host bounds.
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
MAX_FILES, MAX_FILE_BYTES, MAX_REQUEST_BYTES = 100, 5_000_000, 30_000_000


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


def upload_source(connection, tenant, user, names, contents, label, writable, source_id=None, *, upload_id=None,
                  final=True):
    """Store a source's files as its current set; `source_id` refreshes an existing source in one request.

    `writable` marks a PC's connected folder, which only its owner refreshes. A browser upload larger than one
    request opens an upload with its first batch (`final` false, no `upload_id`), adds batches to it by its
    `upload_id`, and makes the whole set current with its final batch.
    """
    try:
        if not isinstance(names, list) or len(names) != len(contents) or not 1 <= len(contents) <= MAX_FILES:
            raise ValueError(f"Choose between 1 and {MAX_FILES} files with their relative paths.")
        names = [safe_path(name) for name in names]
        if len(names) != len(set(names)):
            raise ValueError("Each file's path is chosen once.")
        if not label.strip() or len(label) > 120:
            raise ValueError("Source label must contain 1–120 characters.")
        for name, content in zip(names, contents, strict=True):
            _check(name, content)
        if sum(map(len, contents)) > MAX_REQUEST_BYTES:
            raise ValueError("Upload at most 30 MB at a time.")
        if source_id and (upload_id or not final):
            raise ValueError("A connected folder is refreshed in one request.")
    except (ValueError, TypeError, KeyError) as error:
        raise ServiceError("invalid", str(error)) from error
    if upload_id or not final:
        return _batch(connection, tenant, user, names, contents, label, upload_id, final)
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


def _batch(connection, tenant, user, names, contents, label, upload_id, final):
    """Stage one batch of an upload; the final batch checks the whole set and makes it current at once."""
    if upload_id is None:
        # Uploads abandoned a day ago go with their sources and staged files: none was ever current.
        connection.execute(
            """DELETE FROM account_files WHERE tenant_id=%s AND upload_id IN (SELECT id FROM account_uploads
               WHERE tenant_id=%s AND committed_at IS NULL AND created_at < now() - interval '1 day')""",
            (tenant["id"], tenant["id"]))
        connection.execute(
            """DELETE FROM account_sources WHERE tenant_id=%s AND id IN (SELECT source_id FROM account_uploads
               WHERE tenant_id=%s AND committed_at IS NULL AND created_at < now() - interval '1 day')""",
            (tenant["id"], tenant["id"]))
        source = connection.execute(
            "INSERT INTO account_sources (tenant_id,actor_id,label,writable) VALUES (%s,%s,%s,false) RETURNING *",
            (tenant["id"], user["id"], label)).fetchone()
        upload = connection.execute(
            "INSERT INTO account_uploads (tenant_id,source_id,actor_id) VALUES (%s,%s,%s) RETURNING *",
            (tenant["id"], source["id"], user["id"])).fetchone()
    else:
        upload = connection.execute("SELECT * FROM account_uploads WHERE tenant_id=%s AND id=%s FOR UPDATE",
                                    (tenant["id"], upload_id)).fetchone()
        if upload is None:
            raise ServiceError("not_found", "Upload not found.")
        if upload["actor_id"] != user["id"]:
            raise ServiceError("forbidden", "Only the person who started this upload can add to it.")
        if upload["committed_at"]:
            raise ServiceError("conflict", "This upload is already complete. Start a new one.")
        source = connection.execute("SELECT * FROM account_sources WHERE tenant_id=%s AND id=%s",
                                    (tenant["id"], upload["source_id"])).fetchone()
    staged = {row["path"] for row in connection.execute(
        "SELECT path FROM account_files WHERE tenant_id=%s AND upload_id=%s", (tenant["id"], upload["id"])).fetchall()}
    again = sorted(staged & set(names))
    if again:
        raise ServiceError("invalid", f"{again[0]} is already in this upload. Choose each file once.")
    if len(staged) + len(names) > MAX_FILES:
        raise ServiceError("invalid", f"An upload holds at most {MAX_FILES} files.")
    with connection.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO account_files (tenant_id,source_id,upload_id,path,sha256,content,current)
               VALUES (%s,%s,%s,%s,%s,%s,false)""",
            [(tenant["id"], source["id"], upload["id"], path, hashlib.sha256(content).hexdigest(), content)
             for path, content in zip(names, contents, strict=True)])
    if not final:
        return {"upload_id": upload["id"], "staged": len(staged) + len(names)}
    saved = connection.execute(
        """UPDATE account_files SET current=true WHERE tenant_id=%s AND upload_id=%s RETURNING id,path,sha256""",
        (tenant["id"], upload["id"])).fetchall()
    connection.execute("UPDATE account_uploads SET committed_at=now() WHERE id=%s", (upload["id"],))
    return {"id": source["id"], "label": source["label"], "writable": False,
            "files": sorted(saved, key=lambda row: row["path"])}


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


def described(connection, tenant_id, ids):
    """These files of the tenant as a launch checks them, without their contents: path, whether current, and size."""
    rows = connection.execute(
        """SELECT id, path, current, octet_length(content) AS size FROM account_files
           WHERE tenant_id=%s AND id=ANY(%s::uuid[])""", (tenant_id, ids)).fetchall()
    if len(rows) != len(set(ids)):
        raise ServiceError("not_found", "One or more files are not in this workspace.")
    return rows


def content(connection, tenant_id, file_id):
    """A file's bytes and media type, for viewing it beside its record."""
    file = files_for(connection, tenant_id, [str(file_id)])[0]
    return bytes(file["content"]), MEDIA[Path(file["path"]).suffix.lower()]
