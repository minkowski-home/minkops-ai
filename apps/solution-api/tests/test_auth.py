"""People's accounts over HTTP: no public sign-up, joining by an invitation's link, passwords, profile and sessions."""

import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DEV_MODE", "1")

from people import PASSWORD, person, signed_in  # noqa: E402

from minkops_api.main import app  # noqa: E402

URL = os.environ.get("TEST_DATABASE_URL")


def token_of(link):
    return link.rsplit("/", 1)[-1]


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class AuthTests(unittest.TestCase):
    def invite(self, admin, csrf, slug, email, role="member"):
        sent = admin.post(f"/api/tenants/{slug}/invitations", headers=csrf, json={"email": email, "role": role})
        self.assertEqual(sent.status_code, 201, sent.text)
        return token_of(sent.json()["invitation_link"])

    def login(self, client, email, password=PASSWORD):
        return client.post("/api/auth/login", json={"email": email, "password": password})

    def test_there_is_no_public_sign_up(self):
        client = TestClient(app)
        for path in ("/api/auth/signup", "/api/auth/verify"):
            self.assertIn(client.post(path, json={}).status_code, (404, 405))

    def test_an_invitation_link_creates_the_account_signs_it_in_and_works_once(self):
        admin, csrf, owner = signed_in()
        token = self.invite(admin, csrf, owner["slug"], "New.Person@Example.com")
        newcomer = TestClient(app)
        shown = newcomer.get(f"/api/auth/invitations/{token}").json()
        self.assertEqual((shown["email"], shown["role"], shown["account"]), ("new.person@example.com", "member", False))
        short = newcomer.post(f"/api/auth/invitations/{token}/accept", json={"name": "Ravi", "password": "short"})
        self.assertEqual(short.status_code, 422, short.text)
        joined = newcomer.post(f"/api/auth/invitations/{token}/accept", json={"name": "Ravi", "password": PASSWORD})
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertIn("httponly", joined.headers["set-cookie"].lower())
        me = newcomer.get("/api/auth/me").json()
        self.assertEqual([(m["slug"], m["role"]) for m in me["memberships"]], [(owner["slug"], "member")])
        for attempt in (newcomer.get(f"/api/auth/invitations/{token}"),
                        TestClient(app).post(f"/api/auth/invitations/{token}/accept",
                                             json={"name": "Again", "password": PASSWORD})):
            self.assertEqual(attempt.status_code, 404, attempt.text)

    def test_an_address_with_an_account_signs_in_to_accept(self):
        admin, csrf, owner = signed_in()
        left = person(owner["slug"])
        removed = admin.delete(f"/api/tenants/{owner['slug']}/members/{left['id']}", headers=csrf)
        self.assertEqual(removed.status_code, 200, removed.text)
        other, other_csrf, other_owner = signed_in()
        token = self.invite(other, other_csrf, other_owner["slug"], left["email"])
        self.assertTrue(TestClient(app).get(f"/api/auth/invitations/{token}").json()["account"])
        anonymous = TestClient(app).post(f"/api/auth/invitations/{token}/accept", json={"name": "X", "password": PASSWORD})
        self.assertEqual(anonymous.status_code, 409, anonymous.text)
        self.assertTrue(anonymous.json()["detail"]["sign_in"])
        returning = TestClient(app)
        self.assertEqual(self.login(returning, left["email"]).status_code, 200)
        self.assertEqual(returning.post(f"/api/auth/invitations/{token}/accept", json={}).status_code, 403)
        csrf_header = {"x-csrf-token": returning.get("/api/auth/me").json()["csrf_token"]}
        accepted = returning.post(f"/api/auth/invitations/{token}/accept", headers=csrf_header, json={})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(returning.get("/api/auth/me").json()["memberships"][0]["slug"], other_owner["slug"])

    def test_a_reset_answers_alike_for_any_address_and_its_link_works_once(self):
        account = person()
        elsewhere = TestClient(app)
        self.login(elsewhere, account["email"])
        anonymous = TestClient(app)
        unknown = anonymous.post("/api/auth/password-reset", json={"email": "nobody@example.com"})
        known = anonymous.post("/api/auth/password-reset", json={"email": account["email"]})
        self.assertEqual((unknown.status_code, known.status_code), (202, 202))
        self.assertEqual(unknown.json()["message"], known.json()["message"])
        self.assertNotIn("reset_link", unknown.json())
        token = token_of(known.json()["reset_link"])
        done = anonymous.post("/api/auth/password-reset/confirm", json={"token": token, "password": "a new long password"})
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(elsewhere.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.login(TestClient(app), account["email"], "a new long password").status_code, 200)
        again = anonymous.post("/api/auth/password-reset/confirm", json={"token": token, "password": "another password!"})
        self.assertEqual(again.status_code, 404, again.text)

    def test_a_person_renames_themselves_and_changes_their_password_ending_their_other_sessions(self):
        here, csrf, account = signed_in()
        there = TestClient(app)
        self.login(there, account["email"])
        self.assertEqual(here.patch("/api/auth/me", json={"name": "Asha Rao"}).status_code, 403)
        renamed = here.patch("/api/auth/me", headers=csrf, json={"name": "  Asha   Rao "})
        self.assertEqual(renamed.json()["name"], "Asha Rao")
        wrong = here.post("/api/auth/password", headers=csrf,
                          json={"current_password": "not my password", "new_password": "a new long password"})
        self.assertEqual(wrong.status_code, 422, wrong.text)
        changed = here.post("/api/auth/password", headers=csrf,
                            json={"current_password": PASSWORD, "new_password": "a new long password"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual((here.get("/api/auth/me").status_code, there.get("/api/auth/me").status_code), (200, 401))

    def test_a_person_sees_their_sessions_and_signs_out_the_others(self):
        here, csrf, account = signed_in()
        laptop, phone = TestClient(app), TestClient(app)
        for client in (laptop, phone):
            self.login(client, account["email"])
        listed = here.get("/api/auth/sessions").json()
        self.assertEqual([s["current"] for s in listed], [True, False, False])
        laptop_session = next(s for s in laptop.get("/api/auth/sessions").json() if s["current"])
        self.assertEqual(here.delete(f"/api/auth/sessions/{laptop_session['id']}", headers=csrf).status_code, 200)
        self.assertEqual(laptop.get("/api/auth/me").status_code, 401)
        ended = here.post("/api/auth/sessions/end-others", headers=csrf)
        self.assertEqual(ended.json()["ended"], 1)
        self.assertEqual((here.get("/api/auth/me").status_code, phone.get("/api/auth/me").status_code), (200, 401))

    def test_hosting_proxy_cookie_and_private_api_cache_preserve_login_csrf_and_logout(self):
        account = person()
        client = TestClient(app)
        login = self.login(client, account["email"])
        self.assertIn("__session=", login.headers["set-cookie"])
        # Firebase Hosting forwards only __session. The backend keeps its own
        # opaque PostgreSQL sessions and server-derived CSRF, not Firebase Auth.
        for cookie in list(client.cookies.keys()):
            if cookie != "__session":
                client.cookies.delete(cookie)
        profile = client.get("/api/auth/me")
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.headers["cache-control"], "private, no-store")
        self.assertEqual(client.post("/api/auth/logout").status_code, 403)
        signed_out = client.post("/api/auth/logout", headers={"x-csrf-token": profile.json()["csrf_token"]})
        self.assertEqual(signed_out.status_code, 200, signed_out.text)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)
        self.assertIsNone(client.get("/api/auth/session").json())


if __name__ == "__main__":
    unittest.main()
