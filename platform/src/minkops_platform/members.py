"""Who belongs to a workspace, in which role, and which workflows each member runs (docs/workspace-access.md).

A person belongs to one workspace and joins it by an invitation's link: we invite a workspace's first admin, and its
admins invite everyone else. An admin runs every workflow and manages the workspace's people; a member runs the
workflows an admin assigns them. All of this decides only what people see and do: runs, syncs, saves and memory
never read it, so no change here stops work under way. A workspace always keeps an admin.
"""

import secrets

from psycopg.types.json import Jsonb

from . import clients, desktop, identity
from .errors import ServiceError

ROLES = ("admin", "member")
INVITATION_DAYS = 7


def _audit(connection, tenant_id, event, aggregate_id, actor, **detail):
    connection.execute("INSERT INTO event_outbox(tenant_id,event_type,aggregate_id,payload) VALUES (%s,%s,%s,%s)",
                       (tenant_id, event, aggregate_id,
                        Jsonb({"actor_id": str(actor["id"]) if actor else None, **detail})))


def assigned(connection, tenant, user, member):
    """The workflows this person runs, as {id: key}; None when they run every workflow, as an admin does."""
    if clients.is_admin(user, member):
        return None
    return {row["id"]: row["key"] for row in connection.execute(
        """SELECT w.id, w.key FROM workflow_assignments a JOIN workflows w ON w.tenant_id=a.tenant_id AND w.id=a.workflow_id
           WHERE a.tenant_id=%s AND a.user_id=%s""", (tenant["id"], user["id"]))}


def require_workflow(connection, tenant, user, member, *, workflow_id=None, key=None):
    """Refuse a workflow this person does not run, as if it did not exist."""
    runs = assigned(connection, tenant, user, member)
    if runs is not None and not (workflow_id in runs if key is None else key in runs.values()):
        raise ServiceError("not_found", "Workflow not found.")


# --- invitations --------------------------------------------------------------------------------------------------

def _belongs(connection, email):
    return connection.execute("""SELECT m.tenant_id FROM memberships m JOIN users u ON u.id=m.user_id
                                 WHERE lower(u.email)=lower(%s)""", (email,)).fetchone()


def invite(connection, tenant, actor, email, role):
    """An open invitation to this workspace, with the token its link carries. Inviting an address again replaces
    its link. Someone who belongs to a workspace is not invited: a person belongs to one."""
    email = str(email).strip().lower()
    if role not in ROLES:
        raise ServiceError("invalid", "Invite as an admin or a member.")
    if "@" not in email or len(email) > 254:
        raise ServiceError("invalid", "Give the person's email address.")
    taken = _belongs(connection, email)
    if taken:
        raise ServiceError("conflict", f"{email} is already a member of this workspace." if taken["tenant_id"] == tenant["id"]
                           else f"{email} already belongs to another workspace; a person belongs to one workspace.")
    token = secrets.token_urlsafe(32)
    row = connection.execute(
        """INSERT INTO invitations(tenant_id,email,role,token_hash,expires_at,invited_by)
           VALUES (%s,%s,%s,%s,now() + make_interval(days => %s),%s)
           ON CONFLICT (tenant_id, lower(email)) WHERE accepted_at IS NULL DO UPDATE
           SET role=EXCLUDED.role, token_hash=EXCLUDED.token_hash, expires_at=EXCLUDED.expires_at,
               invited_by=EXCLUDED.invited_by, created_at=now()
           RETURNING id,email,role,expires_at""",
        (tenant["id"], email, role, identity.digest(token), INVITATION_DAYS, actor["id"] if actor else None)).fetchone()
    _audit(connection, tenant["id"], "member.invited", row["id"], actor, role=role)
    return {"invitation": row, "token": token}


def invitations(connection, tenant):
    """The workspace's open invitations, newest first, each saying whether its link has expired."""
    return connection.execute(
        """SELECT i.id, i.email, i.role, i.created_at, i.expires_at, i.expires_at <= now() AS expired,
                  u.name AS invited_by
           FROM invitations i LEFT JOIN users u ON u.id=i.invited_by
           WHERE i.tenant_id=%s AND i.accepted_at IS NULL ORDER BY i.created_at DESC, i.id""",
        (tenant["id"],)).fetchall()


def _open(connection, tenant, invitation_id):
    row = connection.execute("""SELECT * FROM invitations WHERE tenant_id=%s AND id=%s AND accepted_at IS NULL
                                FOR UPDATE""", (tenant["id"], invitation_id)).fetchone()
    if row is None:
        raise ServiceError("not_found", "Invitation not found.")
    return row


def resend(connection, tenant, actor, invitation_id):
    """A new link for an open invitation; the old link stops working."""
    row = _open(connection, tenant, invitation_id)
    return invite(connection, tenant, actor, row["email"], row["role"])


def withdraw(connection, tenant, actor, invitation_id):
    row = _open(connection, tenant, invitation_id)
    connection.execute("DELETE FROM invitations WHERE id=%s", (row["id"],))
    _audit(connection, tenant["id"], "member.invitation_withdrawn", row["id"], actor)


def _invited(connection, token, *, lock=False):
    row = connection.execute(
        f"""SELECT i.*, t.name AS workspace, t.slug FROM invitations i JOIN tenants t ON t.id=i.tenant_id
            WHERE i.token_hash=%s AND i.accepted_at IS NULL AND i.expires_at > now()
            {'FOR UPDATE OF i' if lock else ''}""", (identity.digest(token or ""),)).fetchone()
    if row is None:
        raise ServiceError("not_found", "This invitation link is invalid, used or expired. Ask your workspace "
                                        "admin for a new one.")
    return row


def invitation(connection, token):
    """What a link's page shows: the workspace, address and role, and whether that address has an account."""
    row = _invited(connection, token)
    account = connection.execute("SELECT 1 FROM users WHERE lower(email)=lower(%s)", (row["email"],)).fetchone()
    return {"workspace": row["workspace"], "email": row["email"], "role": row["role"],
            "expires_at": row["expires_at"], "account": account is not None}


def accept(connection, token, *, user=None, name=None, password=None):
    """Join the workspace an invitation names. Signed in, as the invited address; otherwise with a new account,
    verified because the link reached its inbox. An address that has an account signs in first."""
    row = _invited(connection, token, lock=True)
    if user is not None:
        if user["email"].lower() != row["email"].lower():
            raise ServiceError("forbidden", f"This invitation is for {row['email']}. Sign out, then open the link again.")
        person = user
    elif connection.execute("SELECT 1 FROM users WHERE lower(email)=lower(%s)", (row["email"],)).fetchone():
        raise ServiceError("conflict", f"{row['email']} already has an account: sign in, then open this link again.",
                           {"sign_in": True})
    else:
        person = identity.create_account(connection, email=row["email"], name=name, password=password)
    # One workspace per person: a membership taken meanwhile, here or anywhere, leaves this one unmade.
    if connection.execute("""INSERT INTO memberships(tenant_id,user_id,role) VALUES (%s,%s,%s)
                             ON CONFLICT DO NOTHING RETURNING user_id""",
                          (row["tenant_id"], person["id"], row["role"])).fetchone() is None:
        raise ServiceError("conflict", f"{person['email']} already belongs to a workspace; a person belongs to one.")
    connection.execute("UPDATE invitations SET accepted_at=now() WHERE id=%s", (row["id"],))
    _audit(connection, row["tenant_id"], "member.joined", person["id"], person, role=row["role"])
    return {**person, "workspace": row["slug"]}


# --- members ------------------------------------------------------------------------------------------------------

def members(connection, tenant):
    """The workspace's people: each one's role, the workflows a member runs, and their connected PCs."""
    return connection.execute(
        """SELECT u.id, u.name, u.email, m.role, m.created_at AS joined_at,
                  coalesce((SELECT array_agg(a.workflow_id ORDER BY a.workflow_id) FROM workflow_assignments a
                            WHERE a.tenant_id=m.tenant_id AND a.user_id=m.user_id), '{}') AS workflow_ids,
                  (SELECT count(*) FROM desktop_devices d WHERE d.tenant_id=m.tenant_id AND d.owner_id=m.user_id
                       AND d.revoked_at IS NULL) AS pcs
           FROM memberships m JOIN users u ON u.id=m.user_id
           WHERE m.tenant_id=%s ORDER BY m.role, u.name, u.id""", (tenant["id"],)).fetchall()


def _member(connection, tenant, user_id):
    """Lock the workspace's admins, then this member: two admins changing each other at once leave one standing."""
    admins = [row["user_id"] for row in connection.execute(
        "SELECT user_id FROM memberships WHERE tenant_id=%s AND role='admin' ORDER BY user_id FOR UPDATE",
        (tenant["id"],))]
    row = connection.execute(
        """SELECT m.user_id, m.role, u.name FROM memberships m JOIN users u ON u.id=m.user_id
           WHERE m.tenant_id=%s AND m.user_id=%s FOR UPDATE OF m""", (tenant["id"], user_id)).fetchone()
    if row is None:
        raise ServiceError("not_found", "Member not found.")
    return row, admins


def _keeps_an_admin(row, admins):
    if row["role"] == "admin" and admins == [row["user_id"]]:
        raise ServiceError("conflict", f"{row['name']} is this workspace's only admin. Make someone else an admin first.")


def update(connection, tenant, actor, user_id, *, role=None, workflow_ids=None):
    """Change a member's role, or set the workflows they run. An admin runs every workflow, so assignments matter
    once they are a member."""
    row, admins = _member(connection, tenant, user_id)
    if role is not None and role != row["role"]:
        if role not in ROLES:
            raise ServiceError("invalid", "A person is an admin or a member.")
        if role == "member":
            _keeps_an_admin(row, admins)
        connection.execute("UPDATE memberships SET role=%s WHERE tenant_id=%s AND user_id=%s",
                           (role, tenant["id"], user_id))
        _audit(connection, tenant["id"], "member.role_changed", user_id, actor, role=role)
    if workflow_ids is not None:
        wanted = list(dict.fromkeys(workflow_ids))
        found = {r["id"] for r in connection.execute("SELECT id FROM workflows WHERE tenant_id=%s AND id = ANY(%s)",
                                                     (tenant["id"], wanted))}
        if len(found) != len(wanted):
            raise ServiceError("invalid", "Assign only this workspace's workflows.")
        connection.execute("DELETE FROM workflow_assignments WHERE tenant_id=%s AND user_id=%s AND NOT workflow_id = ANY(%s)",
                           (tenant["id"], user_id, wanted))
        connection.execute(
            """INSERT INTO workflow_assignments(tenant_id,workflow_id,user_id,assigned_by)
               SELECT %s, w, %s, %s FROM unnest(%s::uuid[]) AS w ON CONFLICT DO NOTHING""",
            (tenant["id"], user_id, actor["id"] if actor else None, wanted))
        _audit(connection, tenant["id"], "member.workflows_assigned", user_id, actor,
               workflow_ids=[str(w) for w in wanted])
    return next(m for m in members(connection, tenant) if m["id"] == user_id)


def remove(connection, tenant, actor, user_id):
    """Take someone out of the workspace: their assignments and client access go, their sessions end, and their
    PCs are disconnected, so a client's books continue on a replacing PC. Runs they started carry on for others."""
    row, admins = _member(connection, tenant, user_id)
    _keeps_an_admin(row, admins)
    connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (tenant["id"], user_id))
    identity.end_sessions(connection, user_id)
    pcs = desktop.disconnect_owner(connection, tenant["id"], user_id)
    _audit(connection, tenant["id"], "member.removed", user_id, actor, pcs=pcs)
    return {"pcs": pcs}
