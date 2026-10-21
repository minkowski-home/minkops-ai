"""A tenant's files over HTTP: uploaded sources, their current files, and each file's content."""

import json
import os
import unittest

from fastapi.testclient import TestClient

from minkops_api.main import app

URL = os.environ.get("TEST_DATABASE_URL")
PDF = b"%PDF-1.4\n%synthetic bill\n"
CSV = b"Date,Narration,Withdrawal,Deposit,Balance\n01/09/2026,CHARGES,118.00,,98702.00\n"


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class FileSourceTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = URL
        self.client = TestClient(app)
        response = self.client.post("/api/auth/login",
                                    json={"email": "demo@example.com", "password": "long test password 123!"})
        self.assertEqual(response.status_code, 200, response.text)
        self.csrf = {"x-csrf-token": self.client.get("/api/auth/me").json()["csrf_token"]}
        self.base = "/api/tenants/mock-tenant/accounts"

    def upload(self, files, *, csrf=True, **form):
        return self.client.post(self.base + "/sources", headers=self.csrf if csrf else {},
                                data={"label": "Bills", "paths": json.dumps([name for name, _ in files]), **form},
                                files=[("files", (name.rsplit("/", 1)[-1], content)) for name, content in files])

    def test_an_upload_lists_its_current_files_and_serves_each_with_its_type(self):
        response = self.upload([("sep/bill-1.pdf", PDF), ("sep/statement.csv", CSV)])
        self.assertEqual(response.status_code, 200, response.text)
        source = response.json()
        self.assertEqual([f["path"] for f in source["files"]], ["sep/bill-1.pdf", "sep/statement.csv"])
        listed = next(s for s in self.client.get(self.base + "/sources").json() if s["id"] == source["id"])
        self.assertEqual([f["path"] for f in listed["files"]], ["sep/bill-1.pdf", "sep/statement.csv"])
        pdf = self.client.get(f"{self.base}/files/{source['files'][0]['id']}/content")
        self.assertEqual((pdf.status_code, pdf.headers["content-type"], pdf.content), (200, "application/pdf", PDF))
        # Refreshing the source replaces which of its files are current.
        refreshed = self.upload([("sep/bill-2.pdf", PDF + b"2")], source_id=source["id"])
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        listed = next(s for s in self.client.get(self.base + "/sources").json() if s["id"] == source["id"])
        self.assertEqual([f["path"] for f in listed["files"]], ["sep/bill-2.pdf"])

    def test_files_stay_inside_their_tenant_and_a_change_needs_the_csrf_token(self):
        source = self.upload([("bill.pdf", PDF)]).json()
        file_id = source["files"][0]["id"]
        # The demo operator is no member of PR Infra's workspace, so its files are not theirs to read there.
        self.assertIn(self.client.get(f"/api/tenants/pr-infra/accounts/files/{file_id}/content").status_code,
                      (403, 404))
        self.assertEqual(self.upload([("bill.pdf", PDF)], csrf=False).status_code, 403)

    def test_files_that_are_not_what_their_names_claim_or_escape_their_source_are_refused(self):
        refused = {
            "../outside.pdf": [("../outside.pdf", PDF)],
            "an executable": [("setup.exe", b"MZ")],
            "a PDF that is not one": [("bill.pdf", b"<html>")],
            "an image that is not one": [("scan.png", PDF)],
            "a workbook that is not one": [("statement.xlsx", b"PK\x03\x04 not a workbook")],
            "an empty file": [("bill.pdf", b"")],
            "a path given twice": [("bill.pdf", PDF), ("bill.pdf", PDF)],
        }
        for case, files in refused.items():
            with self.subTest(case):
                self.assertEqual(self.upload(files).status_code, 422)


if __name__ == "__main__":
    unittest.main()
