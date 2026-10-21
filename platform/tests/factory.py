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


def company(connection, tenant_row, device_row, client_row=None, *, name=None, status="authorised"):
    return connection.execute(
        """INSERT INTO companies(tenant_id,client_id,device_id,guid,books_from,name,status)
           VALUES (%s,%s,%s,%s,'2026-04-01',%s,%s) RETURNING *""",
        (tenant_row["id"], client_row["id"] if client_row else None, device_row["id"], str(uuid4()),
         name or f"Company {suffix()}", status)).fetchone()


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
