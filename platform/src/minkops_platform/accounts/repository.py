"""Tenant-scoped run observations and immutable source/catalog snapshots."""

import hashlib
import json
from pathlib import PurePosixPath

from minkops_platform.run_controls import observe_task

from minkops_platform.errors import ServiceError

from .catalog import validate_catalog


def digest_bytes(content):
    return hashlib.sha256(content).hexdigest()


def safe_path(path):
    parts = PurePosixPath(path).parts
    if (
        not parts
        or path.startswith("/")
        or "\x00" in path
        or "\\" in path
        or any(p in ("", ".", "..") for p in path.split("/"))
    ):
        raise ValueError("Choose a relative file path inside the selected source.")
    if len(path) > 500:
        raise ValueError("File path is too long.")
    return path


def files_for(connection, tenant_id, ids):
    rows = connection.execute(
        """SELECT f.*, s.writable, s.label FROM account_files f JOIN account_sources s
           ON s.tenant_id=f.tenant_id AND s.id=f.source_id
           WHERE f.tenant_id=%s AND f.id=ANY(%s::uuid[])""",
        (tenant_id, ids),
    ).fetchall()
    if len(rows) != len(set(ids)):
        raise ServiceError("not_found", "One or more files are not in this workspace.")
    return rows


def run_for(connection, tenant_id, run_id, lock=False):
    row = connection.execute(
        "SELECT * FROM account_runs WHERE tenant_id=%s AND id=%s" + (" FOR UPDATE" if lock else ""),
        (tenant_id, run_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Run not found.")
    return row


def observe(connection, run, state, summary, progress):
    connection.execute(
        "UPDATE account_runs SET state=%s, updated_at=now() WHERE tenant_id=%s AND id=%s",
        (state, run["tenant_id"], run["id"]),
    )
    observe_task(
        connection, tenant_id=run["tenant_id"], task_id=run["task_id"], run_id=run["id"],
        state=state, summary=summary, progress=progress, event_prefix="account_run",
    )


def catalog_contents(connection, tenant_id, catalog):
    ids = list({s["file_id"] for s in catalog["sheets"]})
    files = files_for(connection, tenant_id, ids)
    return files, {str(f["id"]): bytes(f["content"]) for f in files}


def resolve_catalog(connection, tenant_id, catalog):
    """Advance confirmed mappings only over our own verified workbook writes.

    An arbitrary external source change requires rediscovery. Our appended rows
    do not change the meaning of a confirmed sheet. Each run pins a new snapshot.
    """
    resolved = json.loads(json.dumps(catalog))
    old_files, _ = catalog_contents(connection, tenant_id, catalog)
    replacements = {}
    for old in old_files:
        current = connection.execute(
            """SELECT * FROM account_files WHERE tenant_id=%s
             AND source_id=%s AND path=%s AND current""",
            (tenant_id, old["source_id"], old["path"]),
        ).fetchone()
        if not current:
            raise ValueError("A catalog source was removed. Refresh discovery.")
        if current["id"] != old["id"]:
            # Trace the complete verified chain, not just the last write.
            chain = connection.execute(
                """SELECT before_sha256,after_sha256 FROM account_writes
                 WHERE tenant_id=%s AND source_id=%s AND path=%s AND verified_at IS NOT NULL""",
                (tenant_id, old["source_id"], old["path"]),
            ).fetchall()
            reachable = {old["sha256"]}
            for _ in range(len(chain)):
                reachable.update(
                    r["after_sha256"] for r in chain if r["before_sha256"] in reachable
                )
            if current["sha256"] not in reachable:
                raise ValueError("Catalog sources changed outside Minkops. Refresh discovery.")
        replacements[str(old["id"])] = str(current["id"])
    for s in resolved["sheets"]:
        s["file_id"] = replacements[s["file_id"]]
    files, contents = catalog_contents(connection, tenant_id, resolved)
    validate_catalog(resolved, contents)
    return resolved, files, contents


def public_run(connection, run):
    value = {k: v for k, v in run.items() if k not in ("request_hash",)}
    value["writes"] = connection.execute(
        """SELECT id,source_id,path,before_sha256,after_sha256,changes,verified_at,cancelled_at
         FROM account_writes WHERE tenant_id=%s AND run_id=%s ORDER BY path""",
        (run["tenant_id"], run["id"]),
    ).fetchall()
    return value


def list_sources(connection, tenant):
    rows = connection.execute(
        "SELECT id,label,writable FROM account_sources WHERE tenant_id=%s ORDER BY created_at",
        (tenant["id"],),
    ).fetchall()
    for row in rows:
        row["files"] = connection.execute(
            """SELECT id,path,sha256 FROM account_files
             WHERE tenant_id=%s AND source_id=%s AND current ORDER BY path""",
            (tenant["id"], row["id"]),
        ).fetchall()
    return rows


def list_catalogs(connection, tenant):
    return connection.execute(
        """SELECT id,catalog,confirmed_at FROM account_catalogs
         WHERE tenant_id=%s ORDER BY confirmed_at DESC""",
        (tenant["id"],),
    ).fetchall()


def list_runs(connection, tenant):
    rows = connection.execute(
        "SELECT * FROM account_runs WHERE tenant_id=%s ORDER BY updated_at DESC LIMIT 50",
        (tenant["id"],),
    ).fetchall()
    return [public_run(connection, row) for row in rows]


def task_run(connection, tenant, task_id):
    row = connection.execute(
        "SELECT * FROM account_runs WHERE tenant_id=%s AND task_id=%s", (tenant["id"], task_id)
    ).fetchone()
    return public_run(connection, row) if row else None
