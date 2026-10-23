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


def same_books(connection, company):
    """The other authorised companies holding this one's books (GUID and BooksFrom), most recently seen first.

    Each names its PC, whether that PC is disconnected, and its client business. A year-split sibling shares the
    GUID but not BooksFrom, so it is other books.
    """
    return connection.execute(
        """SELECT c.*, d.name AS device_name, d.revoked_at IS NOT NULL AS disconnected, cb.slug AS client_slug,
                  cb.name AS client_name
           FROM companies c JOIN desktop_devices d ON d.tenant_id=c.tenant_id AND d.id=c.device_id
           JOIN client_businesses cb ON cb.tenant_id=c.tenant_id AND cb.id=c.client_id
           WHERE c.tenant_id=%s AND c.guid=%s AND c.books_from=%s AND c.status='authorised' AND c.id<>%s
           ORDER BY c.last_seen_at DESC, c.id""",
        (company["tenant_id"], company["guid"], company["books_from"], company["id"])).fetchall()


def predecessor(connection, company, client_id=None):
    """The authorised company a newly found one continues, or None.

    It holds the same books on a PC that is now disconnected. Without a client, it is offered only when one client
    holds such books: which client's they are is otherwise a person's call. Of one client's, the most recently
    seen is the one its runs last worked from.
    """
    gone = [row for row in same_books(connection, company) if row["disconnected"]
            and (client_id is None or row["client_id"] == client_id)]
    return gone[0] if len({row["client_id"] for row in gone}) == 1 else None


def live_copy(connection, company):
    """The authorised company holding these books on another connected PC, or None.

    A client's books are saved to one Tally copy: two copies on two PCs drift apart, and an entry saved to one is
    missing from the other.
    """
    return next((row for row in same_books(connection, company) if not row["disconnected"]), None)


def _pending(connection, tenant, user, member, company_id, status, client=None):
    """The newly found company, locked, and whether this same decision was already made."""
    _require_admin(user, member)
    row = connection.execute("SELECT * FROM companies WHERE tenant_id=%s AND id=%s FOR UPDATE",
                             (tenant["id"], company_id)).fetchone()
    if not row:
        raise ServiceError("not_found", "Company not found.")
    if row["status"] != "pending":
        if row["status"] == status and (client is None or row["client_id"] == client["id"]):
            return row, True
        raise ServiceError("conflict", "This company was already decided. Ask an admin to review it.")
    return row, False


def _set(connection, user, row, status, client=None):
    return connection.execute(
        """UPDATE companies SET status=%s,client_id=%s,decided_by=%s,decided_at=now()
           WHERE id=%s RETURNING *""",
        (status, client["id"] if client else None, user["id"], row["id"])).fetchone()


def _continued(connection, tenant, company_id, client):
    """The company a removed duplicate continued, for the same decision sent again; else None."""
    move = connection.execute(
        """SELECT c.*, m.from_device_id FROM company_moves m JOIN companies c ON c.id=m.company_id
           WHERE m.tenant_id=%s AND m.found_id=%s""", (tenant["id"], company_id)).fetchone()
    if move is None:
        return None
    if move["client_id"] != client["id"]:
        raise ServiceError("conflict", "This company was already decided. Ask an admin to review it.")
    return {**move, "continued_from": move.pop("from_device_id")}


def _continue(connection, user, found, previous):
    """Move the client's company to the PC where its books were found again, and remove the duplicate found there.

    Everything keyed to the company stays with it. The duplicate was never authorised, so nothing refers to it.
    """
    connection.execute("SELECT 1 FROM companies WHERE id=%s FOR UPDATE", (previous["id"],))
    connection.execute("DELETE FROM companies WHERE id=%s", (found["id"],))
    row = connection.execute(
        """UPDATE companies SET device_id=%s,name=%s,company_number=%s,last_seen_at=%s WHERE id=%s RETURNING *""",
        (found["device_id"], found["name"], found["company_number"], found["last_seen_at"], previous["id"])).fetchone()
    connection.execute(
        """INSERT INTO company_moves(tenant_id,found_id,company_id,from_device_id,to_device_id,moved_by)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (row["tenant_id"], found["id"], row["id"], previous["device_id"], row["device_id"], user["id"]))
    return {**row, "continued_from": previous["device_id"]}


def authorise_company(connection, tenant, user, member, company_id, slug):
    """One decision makes a newly found company part of a client's books.

    When the client holds the same books on a disconnected PC, the decision continues that company on this PC
    instead, with its memory, rules and history; the row returned then names the PC it continued from
    (`continued_from`). Authorising for another client starts afresh: one client's memory never reaches another.
    Books another connected PC holds for a client are refused, so a client's entries never split across copies.
    """
    client = require(connection, tenant, user, member, slug)
    try:
        row, decided = _pending(connection, tenant, user, member, company_id, "authorised", client)
    except ServiceError as error:
        # A continuation removed the duplicate it was decided on; the same decision again finds the company.
        replay = error.kind == "not_found" and _continued(connection, tenant, company_id, client)
        if replay:
            return replay
        raise
    if decided:
        return row
    if connection.execute("SELECT 1 FROM desktop_devices WHERE id=%s AND revoked_at IS NOT NULL",
                          (row["device_id"],)).fetchone():
        raise ServiceError("conflict", "The PC that found this company was disconnected. Add it from the PC that "
                                       "holds these books now.")
    # One decision at a time per set of books, so two PCs' copies are never both authorised.
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                       (f"books:{row['tenant_id']}:{row['guid']}:{row['books_from']}",))
    live = live_copy(connection, row)
    if live:
        raise ServiceError("conflict", f"These books are already {live['client_name']}'s on {live['device_name']}. "
                                       f"To move them here, disconnect {live['device_name']} under Connected PCs, "
                                       "then continue them from this card.")
    previous = predecessor(connection, row, client["id"])
    if previous:
        return _continue(connection, user, row, previous)
    return _set(connection, user, row, "authorised", client)


def decline_company(connection, tenant, user, member, company_id):
    row, decided = _pending(connection, tenant, user, member, company_id, "declined")
    return row if decided else _set(connection, user, row, "declined")


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
