"""The opt-in operator must submit clarification and retain review write guards."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "release_verification", Path(__file__).resolve().parents[1] / "verify_production.py"
)
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


@pytest.mark.parametrize("phase", ["bill-clarify", "bill-approve"])
def test_existing_review_routes_clarification_and_blocks_unresolved_approval(tmp_path, monkeypatch, phase):
    (tmp_path / "demo-owner.json").write_text(json.dumps({"email": "owner@example.test", "password": "test"}))
    (tmp_path / "release-bill.json").write_text(json.dumps({"id": "owned-run"}))
    requests = []
    digest = next(iter(verification.REVIEWED_BILLS))

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={}, headers={"set-cookie": "__session=test; Secure"})
        if request.url.path == "/api/auth/me":
            return httpx.Response(200, headers={"cache-control": "private,no-store"}, json={
                "is_platform_admin": False, "csrf_token": "test",
                "memberships": [{"slug": "mock-tenant", "role": "admin"}],
            })
        if request.method == "GET":
            return httpx.Response(200, json={"id": "owned-run", "state": "review", "config": {
                "file_provenance": [{"id": "owned-file", "sha256": digest}],
                "tally_target": {"company": "Test Company"},
            }, "result": {"unresolved": ["invoice reference unclear"], "records": []}})
        if request.url.path.endswith("/resolve-bill"):
            clarification = json.loads(request.content)
            assert clarification["file_id"] == "owned-file"
            assert verification.REVIEWED_BILLS[digest]["tax_ledger"] in clarification["user_input"]
            return httpx.Response(200, json={"id": "owned-run", "state": "queued"})
        assert request.url.path == "/api/auth/logout"
        return httpx.Response(200, json={})

    client = httpx.Client(base_url=verification.ORIGIN, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(verification.httpx, "Client", lambda **kwargs: client)
    if phase == "bill-approve":
        with pytest.raises(AssertionError):
            verification.main(tmp_path, phase, None)
        assert not any(path.endswith("/approve") for _, path in requests)
    else:
        verification.main(tmp_path, phase, None)
        assert ("POST", verification.BASE + "/runs/owned-run/resolve-bill") in requests
        assert json.loads((tmp_path / "release-bill-result.json").read_text())["state"] == "queued"
