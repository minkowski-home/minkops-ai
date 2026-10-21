"""Unique, minimal rows for database-backed rebuild tests.

Every test shares one migrated database, so each helper names its rows with a
fresh suffix and returns plain dicts shaped like the API's own lookups.
"""

import os
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row)


def suffix():
    return uuid4().hex[:10]


def tenant(connection, *, scoping=False):
    tag = suffix()
    return connection.execute(
        "INSERT INTO tenants(slug,name,client_scoping) VALUES (%s,%s,%s) RETURNING id,slug,name,client_scoping",
        (f"t-{tag}", f"Tenant {tag}", scoping)).fetchone()


def user(connection, tenant_row=None, *, role="member", platform_admin=False):
    tag = suffix()
    row = connection.execute(
        """INSERT INTO users(email,name,password_hash,email_verified_at,is_platform_admin)
           VALUES (%s,%s,'unused',now(),%s) RETURNING id,name,email,is_platform_admin""",
        (f"{tag}@example.com", f"User {tag}", platform_admin)).fetchone()
    if tenant_row is not None and role:
        connection.execute("INSERT INTO memberships(tenant_id,user_id,role) VALUES (%s,%s,%s)",
                           (tenant_row["id"], row["id"], role))
    return row


def member(connection, tenant_row, user_row):
    """The membership row tenant_access returns, or None for a platform admin."""
    return connection.execute("SELECT role FROM memberships WHERE tenant_id=%s AND user_id=%s",
                              (tenant_row["id"], user_row["id"])).fetchone()


def client(connection, tenant_row, slug=None):
    slug = slug or f"c-{suffix()}"
    return connection.execute(
        "INSERT INTO client_businesses(tenant_id,slug,name) VALUES (%s,%s,%s) RETURNING *",
        (tenant_row["id"], slug, f"Client {slug}")).fetchone()


def device(connection, tenant_row, owner):
    return connection.execute(
        """INSERT INTO desktop_devices(tenant_id,owner_id,installation_id,name,token_hash)
           VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        (tenant_row["id"], owner["id"], uuid4(), f"PC {suffix()}", uuid4().hex)).fetchone()


def company(connection, tenant_row, device_row, client_row=None, *, name=None, status="authorised", guid=None,
            books_from="2026-04-01"):
    """A company on a PC; a year split shares its GUID with another part, told apart by `books_from`."""
    return connection.execute(
        """INSERT INTO companies(tenant_id,client_id,device_id,guid,books_from,name,status)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (tenant_row["id"], client_row["id"] if client_row else None, device_row["id"], guid or str(uuid4()),
         books_from, name or f"Company {suffix()}", status)).fetchone()


def workflow(connection, tenant_row, key="bill-entry"):
    employee = connection.execute(
        """INSERT INTO employees(tenant_id,key,name) VALUES (%s,'accounts-desk','Accounts desk')
           ON CONFLICT (tenant_id,key) DO UPDATE SET name=EXCLUDED.name RETURNING id""",
        (tenant_row["id"],)).fetchone()
    row = connection.execute(
        """INSERT INTO workflows(tenant_id,key,name,status) VALUES (%s,%s,%s,'active')
           ON CONFLICT (tenant_id,key) DO UPDATE SET status='active' RETURNING *""",
        (tenant_row["id"], key, key.replace("-", " ").capitalize())).fetchone()
    connection.execute("INSERT INTO workflow_employees(tenant_id,workflow_id,employee_id) VALUES (%s,%s,%s) "
                       "ON CONFLICT DO NOTHING", (tenant_row["id"], row["id"], employee["id"]))
    return row


def run(connection, tenant_row, client_row, workflow_row, actor, items, *, key=None, handler="desk.test"):
    """A run launched through the real path, with a small fixed bundle."""
    from minkops_platform import work
    return work.launch(connection, tenant_id=tenant_row["id"], client_id=client_row["id"], workflow=workflow_row,
                       handler=handler, definition_version="1.0.0",
                       bundle={"instructions": "Read the bill.", "tools": ["propose"]}, actor_id=actor["id"],
                       request_key=key or uuid4(), request_hash="h", config={"review_mode": "all_outputs"},
                       title="Bill entry", items=items)


def books(connection, company, masters, vouchers=()):
    """Publish one full mirror version of a company's books: native masters and vouchers."""
    from minkops_platform.accounts import mirror
    version = mirror.begin(connection, company, kind="full", reason="test", markers={"alt_mst_id": 1, "alt_vch_id": 1},
                           coverage={"from": "2026-04-01", "to": "2027-03-31"})
    mirror.upsert_masters(connection, version, list(masters))
    mirror.upsert_vouchers(connection, version, list(vouchers))
    return mirror.publish(connection, version)


def upload(connection, tenant_row, actor, files):
    """Files in one uploaded source, as {name: bytes}; returns their rows in order."""
    import hashlib
    source = connection.execute("INSERT INTO account_sources(tenant_id,actor_id,label) VALUES (%s,%s,'Uploads') RETURNING id",
                                (tenant_row["id"], actor["id"])).fetchone()
    return [connection.execute(
        """INSERT INTO account_files(tenant_id,source_id,path,sha256,content) VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        (tenant_row["id"], source["id"], name, hashlib.sha256(content).hexdigest(), content)).fetchone()
        for name, content in files.items()]


def text_pdf(*pages):
    """A PDF whose pages carry these text lines, one below another, as a text layer."""
    fonts = len(pages) * 2 + 3
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % (3 + 2 * n)
                                                                       for n in range(len(pages))), len(pages))]
    for number, lines in enumerate(pages):
        shown = " ".join(f"({line}) Tj 0 -16 Td" for line in lines)
        stream = f"BT /F1 10 Tf 50 790 Td {shown} ET".encode()
        objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (4 + 2 * number, fonts),
                    b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    body, offsets = b"%PDF-1.4\n", []
    for number, content in enumerate(objects, 1):
        offsets.append(len(body))
        body += b"%d 0 obj\n" % number + content + b"\nendobj\n"
    xref = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o
                                                                                  for o in offsets)
    return body + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
