"""Workflow release checks retry from original evidence and retain write guards."""

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


@pytest.mark.parametrize(
    "phase,problem",
    [
        ("bill-approve", "unresolved"),
        ("bill-approve", "company"),
        ("bill-approve", "record"),
        ("bill-approve", "operation"),
        ("bill-retry", "resolved"),
        ("bill-retry", "company"),
        ("bill-retry", "fixture"),
        ("bill-retry", "state"),
    ],
)
def test_existing_review_blocks_unsafe_approval_or_retry(tmp_path, monkeypatch, phase, problem):
    client, requests = review_client(tmp_path, problem)
    monkeypatch.setattr(verification.httpx, "Client", lambda **kwargs: client)
    with pytest.raises(ValueError):
        verification.main(tmp_path, phase, None)
    assert not any(path.endswith(("/approve", "/resolve-bill")) for _, path in requests)


def review_client(tmp_path, problem=None):
    (tmp_path / "demo-owner.json").write_text(
        json.dumps({"email": "owner@example.test", "password": "test"})
    )
    (tmp_path / "release-bill.json").write_text(json.dumps({"id": "owned-run"}))
    requests = []
    digest = next(iter(verification.REVIEWED_BILLS))

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={}, headers={"set-cookie": "__session=test; Secure"})
        if request.url.path == "/api/auth/me":
            return httpx.Response(
                200,
                headers={"cache-control": "private,no-store"},
                json={
                    "is_platform_admin": False,
                    "csrf_token": "test",
                    "memberships": [{"slug": "mock-tenant", "role": "admin"}],
                },
            )
        if request.method == "GET":
            data = dict(verification.REVIEWED_BILLS[digest])
            if problem == "record":
                data["total"] += 1
            return httpx.Response(
                200,
                json={
                    "id": "owned-run",
                    "state": "queued" if problem == "state" else "review",
                    "config": {
                        "file_provenance": [
                            {
                                "id": "owned-file",
                                "sha256": "unknown" if problem == "fixture" else digest,
                            }
                        ],
                        "tally_target": {
                            "company": "Live Company" if problem == "company" else "Test Company"
                        },
                    },
                    "result": {
                        "unresolved": []
                        if problem in ("resolved", "record", "operation")
                        else [
                            {"source_file_id": "owned-file", "reason": "invoice reference unclear"}
                        ],
                        "records": [
                            {
                                "data": data,
                                "operation": "update" if problem == "operation" else "append",
                            }
                        ],
                    },
                },
            )
        if request.url.path.endswith("/resolve-bill"):
            assert json.loads(request.content) == {"file_id": "owned-file"}
            return httpx.Response(200, json={"id": "owned-run", "state": "queued"})
        if request.url.path.endswith("/approve"):
            approval = json.loads(request.content)
            assert approval["acknowledge_findings"] is True
            assert approval["result"]["records"][0]["data"] == verification.REVIEWED_BILLS[digest]
            return httpx.Response(200, json={"id": "owned-run", "state": "writing"})
        assert request.url.path == "/api/auth/logout"
        return httpx.Response(200, json={})

    return httpx.Client(
        base_url=verification.ORIGIN, transport=httpx.MockTransport(respond)
    ), requests


def test_retry_uses_original_evidence_without_correction_text(tmp_path, monkeypatch):
    client, requests = review_client(tmp_path)
    monkeypatch.setattr(verification.httpx, "Client", lambda **kwargs: client)
    verification.main(tmp_path, "bill-retry", None)
    assert ("POST", verification.BASE + "/runs/owned-run/resolve-bill") in requests
    assert json.loads((tmp_path / "release-bill-result.json").read_text())["state"] == "queued"


def test_reviewed_append_still_submits_approval(tmp_path, monkeypatch):
    client, requests = review_client(tmp_path, "resolved")
    monkeypatch.setattr(verification.httpx, "Client", lambda **kwargs: client)
    verification.main(tmp_path, "bill-approve", None)
    assert ("POST", verification.BASE + "/runs/owned-run/approve") in requests
    assert json.loads((tmp_path / "release-bill-result.json").read_text())["state"] == "writing"
