"""Opt-in owned-demo workflow checks; credentials and results stay private.

After correcting the original system and refreshing discovery, bill-retry reads
the original evidence again. Reviewed fixture values only guard approval; they
are never submitted as agent correction text.
"""

import argparse
import hashlib
import json
import uuid
from pathlib import Path

import httpx

ORIGIN = "https://app.minkops.com"
BASE = "/api/tenants/mock-tenant/accounts"
DECISIONS = "/api/tenants/mock-tenant/attention/bills"
REVIEWED_BILLS = json.loads(Path(__file__).with_name("release-bill-fixtures.json").read_text())


def require(condition, message):
    """Operator authorization guards must remain active under python -O."""
    if not condition:
        raise ValueError(message)


def main(state_dir, phase, invoice):
    credentials = json.loads((state_dir / "demo-owner.json").read_text())
    with httpx.Client(base_url=ORIGIN, timeout=65) as api:
        login = api.post("/api/auth/login", json=credentials)
        login.raise_for_status()
        require("Secure" in login.headers["set-cookie"], "Production login must use a secure cookie")
        profile = api.get("/api/auth/me")
        profile.raise_for_status()
        require("no-store" in profile.headers["cache-control"], "Production identity must not be cached")
        user = profile.json()
        require(not user["is_platform_admin"], "Release checks require the ordinary demo owner")
        require(any(m["slug"] == "mock-tenant" and m["role"] == "admin" for m in user["memberships"]),
                "The release owner must administer the isolated demo tenant")
        api.headers["x-csrf-token"] = user["csrf_token"]
        if phase == "bill-start":
            if not invoice:
                raise ValueError("Supply a reviewed synthetic release fixture")
            content = invoice.read_bytes()
            # Scope this paid release check to the reviewed RC fixture, never
            # arbitrary customer documents or a new financial test identity.
            require(hashlib.sha256(content).hexdigest() in REVIEWED_BILLS, "Only reviewed synthetic fixtures may be tested")
            source = api.post(BASE + "/sources", data={"label": "Synthetic release verification", "paths": json.dumps([invoice.name])},
                              files={"files": (invoice.name, content, "application/pdf")})
            source.raise_for_status()
            discovery = api.get("/api/tenants/mock-tenant/discovery/latest").json()
            require(discovery["ready"] and discovery["config"]["tally"]["company"] == "Test Company",
                    "A ready Test Company catalog is required")
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
            if phase == "bill-retry":
                provenance = result["config"]["file_provenance"]
                require(len(provenance) == 1 and provenance[0]["sha256"] in REVIEWED_BILLS,
                        "Retry requires one reviewed synthetic fixture")
                require(result["state"] == "review" and result["result"]["unresolved"],
                        "Only unresolved reviews may be retried")
                require(result["config"]["tally_target"]["company"] == "Test Company",
                        "Release retry is restricted to Test Company")
                # Recheck is the same audited decision the review screen offers.
                retry = api.post(f"{DECISIONS}/{previous['id']}/{provenance[0]['id']}",
                                 json={"action": "retry"})
                retry.raise_for_status()
                result = retry.json()
            if phase == "bill-approve":
                provenance = result["config"]["file_provenance"]
                require(len(provenance) == 1 and provenance[0]["sha256"] in REVIEWED_BILLS,
                        "Approval requires one reviewed synthetic fixture")
                expected = REVIEWED_BILLS[provenance[0]["sha256"]]
                require(result["state"] == "review", "Only a ready review may be approved")
                require(result["config"]["tally_target"]["company"] == "Test Company",
                        "Release approval is restricted to Test Company")
                require(not result["result"]["unresolved"], "Unresolved bills cannot be approved")
                records = result["result"]["records"]
                require(len(records) == 1 and records[0]["data"] == expected,
                        "The reviewed record must match every expected fixture value")
                require(records[0]["operation"] == "append", "Release checks permit only a reviewed append")
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
    parser.add_argument("phase", choices=["bill-start", "bill-inspect", "bill-approve", "bill-retry"])
    parser.add_argument("--invoice", type=Path)
    args = parser.parse_args()
    main(args.state_dir, args.phase, args.invoice)
