"""Client businesses, per-client access, and the companies authorised for them.

Tenant -> client business -> company. A single business (`client_scoping`
false) lets every member reach every client business; an accounting practice
limits members to the clients granted to them. Tenant and platform admins
reach every client and alone change clients, access and company authorisation.
Callers pass the membership row from tenant_access (None for a platform admin
without one) and own the transaction.
"""

import re

from psycopg.errors import UniqueViolation

from .errors import ServiceError

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


def is_admin(user, member):
    return bool(user.get("is_platform_admin")) or (member is not None and member["role"] == "admin")


def _scoping(connection, tenant):
    return connection.execute("SELECT client_scoping FROM tenants WHERE id=%s", (tenant["id"],)).fetchone()["client_scoping"]


def visible_ids(connection, tenant, user, member):
    """None when the user reaches every client, else the granted client IDs."""
    if is_admin(user, member) or not _scoping(connection, tenant):
        return None
    rows = connection.execute("SELECT client_id FROM client_access WHERE tenant_id=%s AND user_id=%s",
                              (tenant["id"], user["id"])).fetchall()
    return {row["client_id"] for row in rows}


def listing(connection, tenant, user, member):
    visible = visible_ids(connection, tenant, user, member)
    rows = connection.execute("SELECT id,slug,name FROM client_businesses WHERE tenant_id=%s ORDER BY name,slug",
                              (tenant["id"],)).fetchall()
    edit = is_admin(user, member)
    return [{**row, "can_edit": edit} for row in rows if visible is None or row["id"] in visible]


def require(connection, tenant, user, member, slug, *, edit=False):
    """The client business, or a ServiceError the API maps to 404 or 403."""
    row = connection.execute("SELECT * FROM client_businesses WHERE tenant_id=%s AND slug=%s",
                             (tenant["id"], slug)).fetchone()
    if not row:
        raise ServiceError("not_found", "Client business not found.")
    if edit and not is_admin(user, member):
        raise ServiceError("forbidden", "Only workspace admins can change this client business.")
    visible = visible_ids(connection, tenant, user, member)
    if visible is not None and row["id"] not in visible:
        raise ServiceError("forbidden", "You do not have access to this client business.")
    return row


def _require_admin(user, member):
    if not is_admin(user, member):
        raise ServiceError("forbidden", "Only workspace admins can manage client businesses.")


def create(connection, tenant, user, member, slug, name):
    _require_admin(user, member)
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ServiceError("invalid", "Use lowercase letters, digits and hyphens for the client's short name.")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ServiceError("invalid", "Name the client business in 1 to 120 characters.")
    try:
        with connection.transaction():
            return connection.execute(
                "INSERT INTO client_businesses(tenant_id,slug,name) VALUES (%s,%s,%s) RETURNING *",
                (tenant["id"], slug, name.strip())).fetchone()
    except UniqueViolation as error:
        raise ServiceError("conflict", "A client business with this short name already exists.") from error


def ensure(connection, tenant, slug, name):
    """Idempotent creation for installation and seeds, which act as the operator."""
    return connection.execute(
        """INSERT INTO client_businesses(tenant_id,slug,name) VALUES (%s,%s,%s)
           ON CONFLICT (tenant_id,slug) DO UPDATE SET name=EXCLUDED.name RETURNING *""",
        (tenant["id"], slug, name)).fetchone()


def grant(connection, tenant, user, member, slug, user_id):
    _require_admin(user, member)
    client = require(connection, tenant, user, member, slug)
    if not connection.execute("SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s",
                              (tenant["id"], user_id)).fetchone():
        raise ServiceError("invalid", "Grant client access only to members of this workspace.")
    connection.execute(
        """INSERT INTO client_access(tenant_id,client_id,user_id,granted_by) VALUES (%s,%s,%s,%s)
           ON CONFLICT DO NOTHING""", (tenant["id"], client["id"], user_id, user["id"]))
    return {"client": slug, "user_id": str(user_id), "access": "granted"}


def revoke(connection, tenant, user, member, slug, user_id):
    _require_admin(user, member)
    client = require(connection, tenant, user, member, slug)
    connection.execute("DELETE FROM client_access WHERE tenant_id=%s AND client_id=%s AND user_id=%s",
                       (tenant["id"], client["id"], user_id))
    return {"client": slug, "user_id": str(user_id), "access": "revoked"}


def companies(connection, tenant, client):
    """The client's authorised companies, each on the connected PC where it was seen.

    A disconnected PC's companies leave the client's books: its runs would wait on a PC that never answers. The PC
    that replaces it finds the same companies as new, for an admin to authorise.
    """
    return connection.execute(
        """SELECT c.*, d.name AS device_name FROM companies c
           JOIN desktop_devices d ON d.tenant_id=c.tenant_id AND d.id=c.device_id
           WHERE c.tenant_id=%s AND c.client_id=%s AND c.status='authorised' AND d.revoked_at IS NULL
           ORDER BY c.name, c.books_from""",
        (tenant["id"], client["id"])).fetchall()


def _decide(connection, tenant, user, member, company_id, status, client=None):
    _require_admin(user, member)
    row = connection.execute("SELECT * FROM companies WHERE tenant_id=%s AND id=%s FOR UPDATE",
                             (tenant["id"], company_id)).fetchone()
    if not row:
        raise ServiceError("not_found", "Company not found.")
    if row["status"] != "pending":
        if row["status"] == status and (client is None or row["client_id"] == client["id"]):
            return row
        raise ServiceError("conflict", "This company was already decided. Ask an admin to review it.")
    return connection.execute(
        """UPDATE companies SET status=%s,client_id=%s,decided_by=%s,decided_at=now()
           WHERE id=%s RETURNING *""",
        (status, client["id"] if client else None, user["id"], company_id)).fetchone()


def authorise_company(connection, tenant, user, member, company_id, slug):
    """One decision makes a newly seen company part of a client's books."""
    return _decide(connection, tenant, user, member, company_id, "authorised",
                   require(connection, tenant, user, member, slug))


def decline_company(connection, tenant, user, member, company_id):
    return _decide(connection, tenant, user, member, company_id, "declined")


def identity_change(known, observed):
    """How an observed company relates to a known one on the same PC.

    Same GUID and BooksFrom: the same company ('same', or 'renamed' when its
    name or number moved, which rebuilds its mirror). A GUID with another
    BooksFrom is a different company, such as a split sibling: None.
    """
    if known["guid"] != observed["guid"] or str(known["books_from"]) != str(observed["books_from"]):
        return None
    same = known["name"] == observed["name"] and known.get("company_number") == observed.get("company_number")
    return "same" if same else "renamed"
