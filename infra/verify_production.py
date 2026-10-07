"""Opt-in owned-demo release checks; credentials and results stay private."""

import argparse
import hashlib
import json
from pathlib import Path
import uuid

import httpx

ORIGIN = "https://app.minkops.com"
BASE = "/api/tenants/mock-tenant/accounts"
REVIEWED_BILLS = json.loads(Path(__file__).with_name("release-bill-fixtures.json").read_text())


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
                raise ValueError("Supply a reviewed synthetic release fixture")
            content = invoice.read_bytes()
            # Scope this paid release check to the reviewed RC fixture, never
            # arbitrary customer documents or a new financial test identity.
            assert hashlib.sha256(content).hexdigest() in REVIEWED_BILLS
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
            if phase == "bill-clarify":
                provenance = result["config"]["file_provenance"]
                assert len(provenance) == 1 and provenance[0]["sha256"] in REVIEWED_BILLS
                assert result["state"] == "review" and result["result"]["unresolved"]
                assert result["config"]["tally_target"]["company"] == "Test Company"
                clarification = api.post(BASE + f"/runs/{previous['id']}/resolve-bill", json={
                    "file_id": provenance[0]["id"],
                    "user_input": "This is an authorized synthetic release test solely in Test Company, not a commercial transaction. Use the printed billing Ref as the invoice_number; the weighbridge ID is not the invoice number. The synthetic/non-commercial label is intentional test context. Preserve observed amounts and evidence, and leave any other missing or conflicting values unresolved.",
                })
                clarification.raise_for_status()
                result = clarification.json()
            if phase == "bill-approve":
                provenance = result["config"]["file_provenance"]
                assert len(provenance) == 1
                expected = REVIEWED_BILLS[provenance[0]["sha256"]]
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
    parser.add_argument("phase", choices=["bill-start", "bill-inspect", "bill-approve", "bill-clarify"])
    parser.add_argument("--invoice", type=Path)
    args = parser.parse_args()
    main(args.state_dir, args.phase, args.invoice)
