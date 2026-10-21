"""Tenant-scoped immutable execution assets, hydrated only for business work.

Storage triggers pin/deduplicate supplied values. Runtime metadata stays in the
small run row; callers must deliberately hydrate before consuming pinned data.
"""

import hashlib
import json

from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError

FIELDS = ('execution_snapshot', 'instructions_snapshot', 'agent_output_schema',
          'source_catalog_snapshot', 'catalog_snapshot', 'local_discovery_snapshot')


def config_json(connection, tenant_id, config):
    """Adapt configuration after resolving immutable evidence to small references.

    Look up the content digest before sending any native bytes. A hydrated
    metadata update must not resend and reparse the entire catalog in PostgreSQL
    merely to discover an ON CONFLICT duplicate. Recompute identity so in-place
    business changes are pinned as new evidence rather than silently discarded.
    The storage trigger still enforces tenant, field and referential integrity.
    """
    packed = dict(config)
    references = dict(config.get('_assets', {}))
    for field in FIELDS:
        if field not in packed:
            continue
        value = packed.pop(field)
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        digest = hashlib.sha256(b'minkops-runtime-json-v1\0' + encoded.encode()).hexdigest()
        args = (tenant_id, field, digest)
        row = connection.execute('SELECT id FROM workflow_run_assets WHERE tenant_id=%s AND field=%s AND sha256=%s', args).fetchone()
        if not row:
            row = connection.execute('''INSERT INTO workflow_run_assets(tenant_id,field,sha256,content)
                VALUES(%s,%s,%s,%s) ON CONFLICT (tenant_id,field,sha256) DO NOTHING RETURNING id''',
                (*args, Jsonb(value))).fetchone()
            if not row:
                row = connection.execute('SELECT id FROM workflow_run_assets WHERE tenant_id=%s AND field=%s AND sha256=%s', args).fetchone()
        references[field] = str(row['id'])
    if references:
        packed['_assets'] = references
    return Jsonb(packed)


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
