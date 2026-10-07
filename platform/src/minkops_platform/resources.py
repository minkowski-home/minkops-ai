"""Locations of the repository-owned employee contracts."""

from pathlib import Path

from minkops_platform.errors import ServiceError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
