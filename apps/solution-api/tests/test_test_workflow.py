import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "db"))
from seed_demo import seed_demo  # noqa: E402
from main import app  # noqa: E402

URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(URL, "TEST_DATABASE_URL is required")
class TestWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = URL
        seed_demo(URL, "long test password 123!")

    def test_image_extraction_is_mock_tenant_only(self):
        client = TestClient(app)
        image = {"file": ("example.png", b"not-a-real-image", "image/png")}
        self.assertEqual(client.post("/extract_image", files=image).status_code, 404)
        self.assertEqual(client.post(
            "/api/tenants/mock-tenant/test/image-to-excel", files=image,
        ).status_code, 401)
        self.assertEqual(client.post("/api/auth/login", json={
            "email": "demo@example.com", "password": "long test password 123!"
        }).status_code, 200)
        csrf = client.get("/api/auth/me").json()["csrf_token"]
        self.assertEqual(client.post(
            "/api/tenants/pr-infra/test/image-to-excel",
            files=image, headers={"x-csrf-token": csrf},
        ).status_code, 404)
        os.environ.pop("OPENAI_API_KEY", None)
        self.assertEqual(client.post(
            "/api/tenants/mock-tenant/test/image-to-excel",
            files=image, headers={"x-csrf-token": csrf},
        ).status_code, 503)


if __name__ == "__main__":
    unittest.main()
