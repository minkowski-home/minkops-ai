import os
import uuid
import unittest

import psycopg
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DEV_MODE", "1")

from minkops_api.main import app


URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = URL

    def setUp(self):
        self.client = TestClient(app)
        self.suffix = uuid.uuid4().hex[:10]

    def register(self, email, **extra):
        return self.client.post("/api/auth/signup", json={
            "name": "Casey Morgan", "email": email, "password": "long test password 123!",
            **extra,
        })

    def verify(self, response):
        self.assertEqual(response.status_code, 201, response.text)
        link = response.json()["verification_link"]
        token = link.rsplit("/", 1)[-1]
        self.assertEqual(self.client.post("/api/auth/verify", json={"token": token}).status_code, 200)

    def login(self, email):
        return self.client.post("/api/auth/login", json={
            "email": email, "password": "long test password 123!"
        })

    def test_signup_requires_verified_email_and_creates_tenant_admin(self):
        self.assertEqual(self.client.get("/api/auth/session").json(), None)
        email = f"casey-{self.suffix}@example.com"
        response = self.register(email, organization_name=f"Studio {self.suffix}")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.login(email).status_code, 403)
        self.verify(response)
        login = self.login(email)
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("httponly", login.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/auth/me").json()["memberships"][0]["role"], "admin")
        self.assertEqual(self.client.get("/api/auth/session").json()["name"], "Casey Morgan")

    def test_hosting_proxy_cookie_and_private_api_cache_preserve_login_csrf_and_logout(self):
        email = f"hosting-{self.suffix}@example.com"
        self.verify(self.register(email))
        login = self.login(email)
        self.assertIn("__session=", login.headers["set-cookie"])
        # Firebase Hosting forwards only __session. The backend keeps its own
        # opaque PostgreSQL sessions and server-derived CSRF, not Firebase Auth.
        for cookie in list(self.client.cookies.keys()):
            if cookie != "__session":
                self.client.cookies.delete(cookie)
        profile = self.client.get("/api/auth/me")
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.headers["cache-control"], "private, no-store")
        signed_out = self.client.post("/api/auth/logout", headers={"x-csrf-token": profile.json()["csrf_token"]})
        self.assertEqual(signed_out.status_code, 200, signed_out.text)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_verified_domain_suggests_tenant_without_granting_access(self):
        slug = f"known-{self.suffix}"
        domain = f"{self.suffix}.example.org"
        with psycopg.connect(URL) as connection:
            tenant = connection.execute(
                "INSERT INTO tenants (slug, name) VALUES (%s, 'Known') RETURNING id", (slug,)
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO tenant_domains (tenant_id, domain, verified_at) VALUES (%s, %s, now())",
                (tenant, domain),
            )
        email = f"new@{domain}"
        response = self.register(email)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["suggested_tenant"]["slug"], slug)
        self.verify(response)
        self.assertEqual(self.login(email).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").json()["memberships"], [])
        self.assertEqual(self.client.get(f"/api/tenants/{slug}/employees").status_code, 403)

    def test_personal_email_can_request_membership_without_automatic_access(self):
        slug = f"personal-{self.suffix}"
        with psycopg.connect(URL) as connection:
            connection.execute("INSERT INTO tenants (slug, name) VALUES (%s, 'Personal')", (slug,))
        email = f"casey-{self.suffix}@gmail.com"
        response = self.register(email)
        self.verify(response)
        self.assertEqual(self.login(email).status_code, 200)
        csrf = self.client.get("/api/auth/me").json()["csrf_token"]
        request = self.client.post(f"/api/tenants/{slug}/join-requests", headers={"x-csrf-token": csrf})
        self.assertEqual(request.status_code, 201, request.text)
        self.assertEqual(self.client.get(f"/api/tenants/{slug}/employees").status_code, 403)

    def test_admin_approves_request_and_member_can_read_but_not_edit(self):
        admin_email = f"admin-{self.suffix}@example.com"
        self.verify(self.register(admin_email, organization_name=f"Company {self.suffix}"))
        self.assertEqual(self.login(admin_email).status_code, 200)
        slug = self.client.get("/api/auth/me").json()["memberships"][0]["slug"]
        admin_client = self.client

        member_client = TestClient(app)
        member_email = f"member-{self.suffix}@gmail.com"
        signup = member_client.post("/api/auth/signup", json={
            "name": "Morgan Member", "email": member_email, "password": "long test password 123!"
        })
        self.assertEqual(signup.status_code, 201)
        token = signup.json()["verification_link"].rsplit("/", 1)[-1]
        self.assertEqual(member_client.post("/api/auth/verify", json={"token": token}).status_code, 200)
        self.assertEqual(member_client.post("/api/auth/login", json={
            "email": member_email, "password": "long test password 123!"
        }).status_code, 200)
        member_csrf = member_client.get("/api/auth/me").json()["csrf_token"]
        self.assertEqual(member_client.post(
            f"/api/tenants/{slug}/join-requests", headers={"x-csrf-token": member_csrf}
        ).status_code, 201)
        admin_csrf = admin_client.get("/api/auth/me").json()["csrf_token"]
        pending = admin_client.get(f"/api/tenants/{slug}/join-requests")
        self.assertEqual(pending.status_code, 200, pending.text)
        request_id = pending.json()[0]["id"]
        approved = admin_client.post(
            f"/api/tenants/{slug}/join-requests/{request_id}/approve",
            headers={"x-csrf-token": admin_csrf},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(member_client.get(f"/api/tenants/{slug}/employees").status_code, 200)
        self.assertEqual(member_client.get("/api/auth/me").json()["memberships"][0]["role"], "member")
        self.assertEqual(member_client.post(
            f"/api/tenants/{slug}/join-requests/{request_id}/approve",
            headers={"x-csrf-token": member_csrf},
        ).status_code, 403)

    def test_mutation_requires_csrf(self):
        email = f"csrf-{self.suffix}@example.com"
        self.verify(self.register(email, organization_name=f"CSRF {self.suffix}"))
        self.login(email)
        slug = self.client.get("/api/auth/me").json()["memberships"][0]["slug"]
        self.assertEqual(self.client.post(f"/api/tenants/{slug}/join-requests").status_code, 403)

    def test_invitation_links_personal_email_to_tenant(self):
        admin_email = f"invite-admin-{self.suffix}@example.com"
        self.verify(self.register(admin_email, organization_name=f"Invite {self.suffix}"))
        self.login(admin_email)
        admin_client = self.client
        me = admin_client.get("/api/auth/me").json()
        slug = me["memberships"][0]["slug"]
        invitee_email = f"invitee-{self.suffix}@gmail.com"
        invited = admin_client.post(
            f"/api/tenants/{slug}/invitations",
            headers={"x-csrf-token": me["csrf_token"]},
            json={"email": invitee_email, "role": "member"},
        )
        self.assertEqual(invited.status_code, 201, invited.text)
        token = invited.json()["invitation_link"].rsplit("/", 1)[-1]
        invitee = TestClient(app)
        signup = invitee.post("/api/auth/signup", json={
            "name": "Invited User", "email": invitee_email, "password": "long test password 123!"
        })
        verify_token = signup.json()["verification_link"].rsplit("/", 1)[-1]
        invitee.post("/api/auth/verify", json={"token": verify_token})
        invitee.post("/api/auth/login", json={
            "email": invitee_email, "password": "long test password 123!"
        })
        csrf = invitee.get("/api/auth/me").json()["csrf_token"]
        accepted = invitee.post("/api/auth/accept-invite", headers={"x-csrf-token": csrf},
                               json={"token": token})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(invitee.get("/api/auth/me").json()["memberships"][0]["slug"], slug)


if __name__ == "__main__":
    unittest.main()
