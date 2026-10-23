"""Signed-in test clients, made the way accounts are: verified, and in one workspace each."""

import os
import uuid

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from minkops_api.main import app
from minkops_platform import identity

PASSWORD = "long test password 123!"


def person(slug=None, role="member"):
    """A new verified account: in workspace `slug` with `role`, or the admin of a new workspace when no slug is
    given. Returns the account with its workspace's slug."""
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as c:
        account = identity.create_account(c, email=f"{uuid.uuid4().hex}@example.com", name="Test Person",
                                          password=PASSWORD)
        tenant = (c.execute("SELECT id, slug FROM tenants WHERE slug=%s", (slug,)) if slug else c.execute(
            "INSERT INTO tenants(slug,name) VALUES (%s,'Test workspace') RETURNING id, slug",
            (f"w-{uuid.uuid4().hex[:10]}",))).fetchone()
        c.execute("INSERT INTO memberships(tenant_id,user_id,role) VALUES (%s,%s,%s)",
                  (tenant["id"], account["id"], role if slug else "admin"))
    return {**account, "slug": tenant["slug"]}


def signed_in(slug=None, role="member"):
    """A client signed in as a new person (`person`), its CSRF header, and the person."""
    account = person(slug, role)
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"email": account["email"], "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"x-csrf-token": client.get("/api/auth/me").json()["csrf_token"]}, account
