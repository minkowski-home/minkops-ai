"""The one transactional boundary for releasing a queued run dependency.

Readiness columns and the database wake-up trigger change in the same update.
The caller commits the decision/audit with this release; dispatch runs afterward.
"""

from psycopg import sql
from psycopg.types.json import Jsonb

FIELDS = {"profile": "awaited_profile_id", "layout_run": "awaited_layout_run_id"}


def release(connection, tenant_id, kind, dependency_id, patch, *, run_id=None, merge_fields=()):
    column = FIELDS[kind]
    expression = sql.SQL("(config-'awaits') || %s::jsonb")
    parameters = [Jsonb(patch)]
    for field in merge_fields:
        expression = sql.SQL("jsonb_set({},ARRAY[%s],coalesce(config->%s,'{{}}'::jsonb) || %s::jsonb)").format(expression)
        parameters.extend((field, field, Jsonb(patch[field])))
    return connection.execute(sql.SQL("""UPDATE workflow_runs SET
        config={},updated_at=now()
        WHERE tenant_id=%s AND state='queued' AND {}=%s
          AND (%s::uuid IS NULL OR id=%s::uuid) RETURNING id,parent_run_id""").format(expression, sql.Identifier(column)),
        (*parameters, tenant_id, str(dependency_id), run_id, run_id)).fetchall()


def release_run(connection, tenant_id, run_id, patch):
    """Release a compound dependency only after its owner proves every part."""
    return connection.execute("""UPDATE workflow_runs SET config=(config-'awaits') || %s::jsonb,updated_at=now()
        WHERE tenant_id=%s AND id=%s AND state='queued' AND blocked RETURNING id,parent_run_id""",
        (Jsonb(patch), tenant_id, run_id)).fetchall()
