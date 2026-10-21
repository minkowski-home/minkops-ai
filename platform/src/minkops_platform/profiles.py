"""Client profiles: learned client practice, derived once, then reused.

Workflow-agnostic storage for what an AI step concluded about one client scope
(a company's posting pattern, a statement layout) so later runs reuse it instead
of deriving it again. A profile becomes `active` only when code proved it or a
member confirmed it. One live version per scope makes derivation single-flight:
concurrent batches that need the same scope wait for one derivation.
"""

from psycopg.types.json import Jsonb

LIVE = ("deriving", "proposed", "active")
MISS_LIMIT = 3


def current(connection, tenant_id, kind, scope_key, *, lock=False):
    """The live version of a scope, if any."""
    return connection.execute(
        f"""SELECT * FROM client_profiles WHERE tenant_id=%s AND kind=%s AND scope_key=%s
        AND status IN ('deriving','proposed','active'){' FOR UPDATE' if lock else ''}""",
        (tenant_id, kind, scope_key),
    ).fetchone()


def get(connection, tenant_id, profile_id, *, lock=False):
    return connection.execute(
        f"SELECT * FROM client_profiles WHERE tenant_id=%s AND id=%s{' FOR UPDATE' if lock else ''}",
        (tenant_id, profile_id),
    ).fetchone()


def ensure(connection, tenant_id, kind, scope_key, *, actor, provenance):
    """The live version, or a new `deriving` one; returns (profile, created).

    Exactly one caller creates the deriving row; the rest receive it and wait.
    """
    version = connection.execute(
        "SELECT coalesce(max(version),0)+1 AS v FROM client_profiles WHERE tenant_id=%s AND kind=%s AND scope_key=%s",
        (tenant_id, kind, scope_key),
    ).fetchone()["v"]
    created = connection.execute(
        """INSERT INTO client_profiles(tenant_id,kind,scope_key,version,status,provenance,created_by)
        VALUES (%s,%s,%s,%s,'deriving',%s,%s)
        ON CONFLICT (tenant_id,kind,scope_key) WHERE status IN ('deriving','proposed','active') DO NOTHING
        RETURNING *""",
        (tenant_id, kind, scope_key, version, Jsonb(provenance), actor),
    ).fetchone()
    if created:
        return created, True
    return current(connection, tenant_id, kind, scope_key), False


def create(connection, tenant_id, kind, scope_key, payload, *, status, actor, provenance):
    """A directly proven version (no derivation), replacing no live version."""
    version = connection.execute(
        "SELECT coalesce(max(version),0)+1 AS v FROM client_profiles WHERE tenant_id=%s AND kind=%s AND scope_key=%s",
        (tenant_id, kind, scope_key),
    ).fetchone()["v"]
    return connection.execute(
        """INSERT INTO client_profiles(tenant_id,kind,scope_key,version,status,payload,provenance,created_by,
            confirmed_by,confirmed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='active' THEN now() END) RETURNING *""",
        (tenant_id, kind, scope_key, version, status, Jsonb(payload), Jsonb(provenance), actor,
         actor if status == "active" else None, status),
    ).fetchone()


def _transition(connection, profile, status, **fields):
    assignments = ", ".join(f"{key}=%s" for key in fields)
    return connection.execute(
        f"UPDATE client_profiles SET status=%s,{assignments + ',' if assignments else ''}updated_at=now() "
        "WHERE tenant_id=%s AND id=%s RETURNING *",
        (status, *(Jsonb(v) if isinstance(v, (dict, list)) else v for v in fields.values()),
         profile["tenant_id"], profile["id"]),
    ).fetchone()


def update_payload(connection, profile, payload):
    """Amend a proposed profile before it is confirmed, such as with a member's answer."""
    if profile["status"] != "proposed":
        raise ValueError("Only a proposed profile can be amended.")
    return connection.execute(
        "UPDATE client_profiles SET payload=%s,updated_at=now() WHERE tenant_id=%s AND id=%s RETURNING *",
        (Jsonb(payload), profile["tenant_id"], profile["id"])).fetchone()


def propose(connection, profile, payload, *, derivation_run_id=None):
    if profile["status"] != "deriving":
        raise ValueError("Only a deriving profile can be proposed.")
    return _transition(connection, profile, "proposed", payload=payload, derivation_run_id=derivation_run_id)


def confirm(connection, profile, actor):
    if profile["status"] != "proposed":
        raise ValueError("Only a proposed profile can be confirmed.")
    return _transition(connection, profile, "active", confirmed_by=actor,
                       confirmed_at=connection.execute("SELECT now() AS n").fetchone()["n"])


def decline(connection, profile, reason):
    return _transition(connection, profile, "superseded", invalidated_reason=reason)


def fail(connection, profile, reason):
    """A failed derivation releases its scope so the next need derives again."""
    return _transition(connection, profile, "failed", invalidated_reason=reason)


def invalidate(connection, profile, reason):
    return _transition(connection, profile, "invalidated", invalidated_reason=reason)


def reprove(connection, profile, provenance):
    """Keep an active profile that still holds against newer evidence."""
    return connection.execute(
        "UPDATE client_profiles SET provenance=%s,updated_at=now() WHERE tenant_id=%s AND id=%s RETURNING *",
        (Jsonb(provenance), profile["tenant_id"], profile["id"]),
    ).fetchone()


def record_miss(connection, profile, count=1):
    """Documents that do not fit an active profile; repeated misses retire it."""
    updated = connection.execute(
        "UPDATE client_profiles SET miss_count=miss_count+%s,updated_at=now() WHERE tenant_id=%s AND id=%s RETURNING *",
        (count, profile["tenant_id"], profile["id"]),
    ).fetchone()
    if updated["status"] == "active" and updated["miss_count"] >= MISS_LIMIT:
        return invalidate(connection, updated, f"{updated['miss_count']} documents did not fit this pattern.")
    return updated
