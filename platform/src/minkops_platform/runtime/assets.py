"""Tenant-scoped immutable execution assets, hydrated only for business work.

Storage triggers pin/deduplicate supplied values. Runtime metadata stays in the
small run row; callers must deliberately hydrate before consuming pinned data.
"""

from minkops_platform.errors import ServiceError


def hydrate(connection, run, *, fields=None):
    if not run:
        return run
    config = run["config"]
    references = {key: value for key, value in config.get("_assets", {}).items()
                  if (fields is None or key in fields) and key not in config}
    if not references:
        return run
    rows = connection.execute("""SELECT id,field,content FROM workflow_run_assets
        WHERE tenant_id=%s AND id=ANY(%s::uuid[])""", (run["tenant_id"], list(references.values()))).fetchall()
    found = {str(row["id"]): row for row in rows}
    if any(value not in found or found[value]["field"] != key for key, value in references.items()):
        raise ServiceError("conflict", "Pinned execution evidence is unavailable. Start a new run explicitly.")
    run["config"] = {**config, **{key: found[value]["content"] for key, value in references.items()}}
    return run


def profile_identity(config):
    """Compute-reuse identity without serializing entire pinned discovery again."""
    import hashlib
    import json

    fields = ("execution_snapshot", "source_catalog_snapshot", "catalog_snapshot")
    assets = config.get("_assets", {})
    pinned = {key: assets.get(key) or config.get(key) for key in fields}
    pinned["authorized_bindings"] = config.get("authorized_bindings")
    return hashlib.sha256(json.dumps(pinned, sort_keys=True, default=str).encode()).hexdigest()
