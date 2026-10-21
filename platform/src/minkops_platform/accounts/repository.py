"""Tenant-scoped run observations and immutable source/catalog snapshots."""

import hashlib
from pathlib import PurePosixPath

from minkops_platform.resources import files_for as files_for
from minkops_platform.runtime.store import observe as observe
from minkops_platform.runtime.store import run_for as run_for


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


def public_run(connection, run):
    from minkops_platform.runtime.store import public_run as shared_public_run

    return shared_public_run(connection, run)


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
    """Recent top-level runs as summaries; full detail is fetched per run.

    Each run pins multi-megabyte discovery snapshots in its config, so a list of
    full runs outgrew hosted response limits after a few dozen runs.
    """
    return connection.execute(
        """SELECT r.id, r.task_id, r.workflow_key, r.definition_version, r.state, r.error, r.updated_at,
               t.control_state,
               CASE WHEN jsonb_typeof(r.result->'records')='array' THEN jsonb_array_length(r.result->'records') ELSE 0 END AS records,
               CASE WHEN jsonb_typeof(r.result->'unresolved')='array' THEN jsonb_array_length(r.result->'unresolved') ELSE 0 END AS unresolved
        FROM account_runs r JOIN tasks t ON t.tenant_id=r.tenant_id AND t.id=r.task_id
        WHERE r.tenant_id=%s AND r.parent_run_id IS NULL ORDER BY r.updated_at DESC LIMIT 50""",
        (tenant["id"],),
    ).fetchall()


def task_run(connection, tenant, task_id):
    row = connection.execute(
        "SELECT * FROM account_runs WHERE tenant_id=%s AND task_id=%s AND parent_run_id IS NULL",
        (tenant["id"], task_id),
    ).fetchone()
    return public_run(connection, row) if row else None


def public_run_for(connection, tenant_id, run_id):
    """A status read does not hydrate private immutable execution evidence."""
    return public_run(connection, run_for(connection, tenant_id, run_id, hydrate_assets=False))
