"""Opt-in owned-demo release checks; credentials and results stay private."""

import argparse
import hashlib
import json
from pathlib import Path
import uuid

import httpx

ORIGIN = "https://app.minkops.com"
BASE = "/api/tenants/mock-tenant/accounts"


def main(state_dir, phase, invoice):
    credentials = json.loads((state_dir / "demo-owner.json").read_text())
    with httpx.Client(base_url=ORIGIN, timeout=65) as api:
        login = api.post("/api/auth/login", json=credentials)
        login.raise_for_status()
        assert "Secure" in login.headers["set-cookie"]
        profile = api.get("/api/auth/me")
        profile.raise_for_status()
        assert "no-store" in profile.headers["cache-control"]
        user = profile.json()
        assert not user["is_platform_admin"]
        assert any(m["slug"] == "mock-tenant" and m["role"] == "admin" for m in user["memberships"])
        api.headers["x-csrf-token"] = user["csrf_token"]
        if phase == "bill-start":
            if not invoice:
                raise ValueError("Supply the reviewed synthetic cement fixture")
            content = invoice.read_bytes()
            # Scope this paid release check to the reviewed RC fixture, never
            # arbitrary customer documents or a new financial test identity.
            assert hashlib.sha256(content).hexdigest() == "393404a002017f01bb8cd4fa5c250e9b9c7a1d8072b0b7cc8ec9644eeeac0b5d"
            source = api.post(BASE + "/sources", data={"label": "Synthetic release verification", "paths": json.dumps([invoice.name])},
                              files={"files": (invoice.name, content, "application/pdf")})
            source.raise_for_status()
            discovery = api.get("/api/tenants/mock-tenant/discovery/latest").json()
            assert discovery["ready"] and discovery["config"]["tally"]["company"] == "Test Company"
            run = api.post(BASE + "/runs", json={"key": "bill-entry", "request_key": str(uuid.uuid4()),
                           "file_ids": [source.json()["files"][0]["id"]],
                           "config": {"output_mode": "tally_in_place", "discovery_id": discovery["id"]}})
            run.raise_for_status()
            result = run.json()
            (state_dir / "release-bill.json").write_text(json.dumps(result))
            print(json.dumps({"bill_run": result["id"], "state": result["state"]}))
        else:
            previous = json.loads((state_dir / "release-bill.json").read_text())
            run = api.get(BASE + f"/runs/{previous['id']}")
            run.raise_for_status()
            result = run.json()
            if phase == "bill-approve":
                expected = {"tax": 7056, "date": "2026-10-01", "total": 32256,
                            "vendor": "RC Deccan Cement Traders", "subtotal": 25200,
                            "cost_code": None, "tax_ledger": "RC Input GST Mock",
                            "invoice_number": "RC26-CEM-041",
                            "purchase_ledger": "RC Civil Materials Purchase"}
                assert result["state"] == "review"
                assert result["config"]["tally_target"]["company"] == "Test Company"
                assert not result["result"]["unresolved"]
                records = result["result"]["records"]
                assert len(records) == 1 and records[0]["data"] == expected
                assert records[0]["operation"] == "append"
                approval = api.post(BASE + f"/runs/{previous['id']}/approve",
                                    json={"result": result["result"], "acknowledge_findings": True})
                approval.raise_for_status()
                result = approval.json()
            (state_dir / "release-bill-result.json").write_text(json.dumps(result))
            print(json.dumps({"bill_run": result["id"], "state": result["state"], "error": result.get("error")}))
        api.post("/api/auth/logout", json={}).raise_for_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("phase", choices=["bill-start", "bill-inspect", "bill-approve"])
    parser.add_argument("--invoice", type=Path)
    args = parser.parse_args()
    main(args.state_dir, args.phase, args.invoice)
