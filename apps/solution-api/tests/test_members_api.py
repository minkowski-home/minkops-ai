"""A workspace's people over HTTP: admins invite, change roles, assign workflows and remove; members cannot."""

import os
import unittest
import uuid

import psycopg
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DEV_MODE", "1")

from people import PASSWORD, person, signed_in  # noqa: E402

from minkops_api.main import app  # noqa: E402

URL = os.environ.get("TEST_DATABASE_URL")


def workflows(slug):
    """The Accounts desk's two workflows in this workspace, by key."""
    with psycopg.connect(URL) as c:
        tenant = c.execute("SELECT id FROM tenants WHERE slug=%s", (slug,)).fetchone()[0]
        c.execute("INSERT INTO employees(tenant_id,key,name) VALUES (%s,'accounts-desk','Accounts desk')", (tenant,))
        return {key: str(c.execute("INSERT INTO workflows(tenant_id,key,name,description) VALUES (%s,%s,%s,'') "
                                   "RETURNING id", (tenant, key, key)).fetchone()[0])
                for key in ("bill-entry", "statement-entry")}


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class MembersTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.csrf, self.owner = signed_in()
        self.base = f"/api/tenants/{self.owner['slug']}"

    def test_admins_invite_resend_and_withdraw_and_members_cannot(self):
        sent = self.admin.post(self.base + "/invitations", headers=self.csrf,
                               json={"email": f"{uuid.uuid4().hex}@example.com", "role": "admin"})
        self.assertEqual(sent.status_code, 201, sent.text)
        first = sent.json()["invitation_link"].rsplit("/", 1)[-1]
        [listed] = self.admin.get(self.base + "/invitations").json()
        self.assertEqual((listed["role"], listed["expired"], listed["invited_by"]), ("admin", False, "Test Person"))
        again = self.admin.post(self.base + f"/invitations/{listed['id']}/resend", headers=self.csrf)
        self.assertEqual(again.status_code, 200, again.text)
        visitor = TestClient(app)
        self.assertEqual(visitor.get(f"/api/auth/invitations/{first}").status_code, 404)
        second = again.json()["invitation_link"].rsplit("/", 1)[-1]
        self.assertEqual(visitor.get(f"/api/auth/invitations/{second}").status_code, 200)
        self.assertEqual(self.admin.delete(self.base + f"/invitations/{listed['id']}", headers=self.csrf).status_code, 200)
        self.assertEqual(visitor.get(f"/api/auth/invitations/{second}").status_code, 404)
        member, member_csrf, _ = signed_in(self.owner["slug"])
        for response in (member.get(self.base + "/members"), member.get(self.base + "/invitations"),
                         member.post(self.base + "/invitations", headers=member_csrf,
                                     json={"email": "x@example.com", "role": "member"})):
            self.assertEqual(response.status_code, 403, response.text)

    def test_a_person_in_another_workspace_is_not_invited(self):
        elsewhere = person()
        refused = self.admin.post(self.base + "/invitations", headers=self.csrf,
                                  json={"email": elsewhere["email"], "role": "member"})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("belongs to one workspace", refused.json()["detail"])

    def test_roles_change_but_the_last_admin_stays(self):
        colleague = person(self.owner["slug"])
        promoted = self.admin.patch(self.base + f"/members/{colleague['id']}", headers=self.csrf, json={"role": "admin"})
        self.assertEqual(promoted.json()["role"], "admin")
        demoted = self.admin.patch(self.base + f"/members/{colleague['id']}", headers=self.csrf, json={"role": "member"})
        self.assertEqual(demoted.json()["role"], "member")
        alone = self.admin.patch(self.base + f"/members/{self.owner['id']}", headers=self.csrf, json={"role": "member"})
        self.assertEqual(alone.status_code, 409, alone.text)
        self.assertEqual(self.admin.delete(self.base + f"/members/{self.owner['id']}", headers=self.csrf).status_code, 409)

    def test_assigned_workflows_and_a_removal_that_signs_out_and_disconnects(self):
        flows = workflows(self.owner["slug"])
        member, member_csrf, colleague = signed_in(self.owner["slug"])
        assigned = self.admin.patch(self.base + f"/members/{colleague['id']}", headers=self.csrf,
                                    json={"workflow_ids": [flows["bill-entry"]]})
        self.assertEqual(assigned.json()["workflow_ids"], [flows["bill-entry"]])
        paired = member.post(self.base + "/desktop/devices", headers=member_csrf,
                             json={"name": "Member PC", "installation_id": str(uuid.uuid4())})
        self.assertEqual(paired.status_code, 201, paired.text)
        [row] = [m for m in self.admin.get(self.base + "/members").json() if m["id"] == str(colleague["id"])]
        self.assertEqual(row["pcs"], 1)
        removed = self.admin.delete(self.base + f"/members/{colleague['id']}", headers=self.csrf)
        self.assertEqual(removed.json(), {"pcs": 1})
        self.assertEqual(member.get("/api/auth/me").status_code, 401)
        self.assertEqual(TestClient(app).post("/api/auth/login", json={"email": colleague["email"], "password": PASSWORD}
                                              ).status_code, 200)
        worker = TestClient(app).post("/api/desktop/worker/heartbeat",
                                      headers={"Authorization": "Bearer " + paired.json()["credential"]})
        self.assertEqual(worker.status_code, 401, worker.text)


if __name__ == "__main__":
    unittest.main()
