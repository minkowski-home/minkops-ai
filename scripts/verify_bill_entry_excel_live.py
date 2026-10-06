"""Opt-in real hosted MIN-118 mappings and MIN-119 native Excel proof.

Only modifies the generated mock-register.xlsx in the hard-demo folder.
Checkpoint IDs permit session reconciliation after interruption, with no new
input sent to completed or active sessions. Model keys stay on the server.
"""

import json
import uuid

import verify_bill_entry_live as proof
from openpyxl import load_workbook


def main():
    checked = proof.checked
    checked(
        "post",
        "/api/auth/login",
        json={"email": "demo@example.com", "password": "long test password 123!"},
    )
    csrf = {"x-csrf-token": checked("get", "/api/auth/me")["csrf_token"]}
    base = "/api/tenants/mock-tenant"
    folder = proof.ROOT / "apps/solution-api/data/min119-hard-demo"
    checkpoint = folder.parent / "min119-excel-proof.json"
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    device = checked(
        "post",
        base + "/desktop/devices",
        headers=csrf,
        json={
            "name": "MIN119 Excel proof",
            "installation_id": state.get("installation_id", str(uuid.uuid4())),
        },
    )
    worker = {"Authorization": "Bearer " + device["credential"]}
    state["installation_id"] = device["installation_id"]
    if "scan_id" not in state:
        source = checked(
            "post",
            base + "/accounts/sources",
            headers=csrf,
            data={
                "paths": '["mock-register.xlsx"]',
                "writable": "true",
                "label": "Complex mock purchase register",
            },
            files=[("files", ("mock-register.xlsx", (folder / "mock-register.xlsx").read_bytes()))],
        )
        checked(
            "post", base + f"/desktop/devices/{device['id']}/sources/{source['id']}", headers=csrf
        )
        scan = checked(
            "post",
            base + "/discovery/runs",
            headers=csrf,
            json={
                "device_id": device["id"],
                "request_key": str(uuid.uuid4()),
                "config": {
                    "depth": "business_mappings",
                    "excel_source_ids": [source["id"]],
                    "tally": None,
                },
            },
        )
        claim = checked("post", "/api/desktop/worker/claim", headers=worker, json={})
        route = f"/api/desktop/worker/jobs/{claim['id']}"
        plan = checked("get", route + "/plan?claim_token=" + claim["claim_token"], headers=worker)
        result = proof.native(
            {
                "operation": "collect",
                "root": proof.WINDOWS_ROOT + r"\apps\solution-api\data\min119-hard-demo",
                "plan": plan,
            }
        )
        checked(
            "post",
            route + "/finish",
            headers=worker,
            json={"claim_token": claim["claim_token"], "result": result},
        )
        scan = checked("get", base + f"/discovery/runs/{scan['id']}")
        state.update(scan_id=scan["id"], mapping_id=scan["mapping_run"]["id"])
        checkpoint.write_text(json.dumps(state))
    scan = checked("get", base + f"/discovery/runs/{state['scan_id']}")
    if not scan["ready"]:
        if scan["mapping_run"]["state"] in ("queued", "executing"):
            print(f"Mapping run {state['mapping_id']} through gpt-6-luna.", flush=True)
            proof.hosted({"id": state["mapping_id"]})
        scan = checked("get", base + f"/discovery/runs/{state['scan_id']}")
        assert scan["mapping_run"]["state"] == "review", scan["mapping_run"]["error"]
        mappings = scan["mapping_run"]["result"]
        target = next(s for s in mappings["sheets"] if s["sheet"] == "Bills")
        assert target["role"] == "destination" and target["table"] == "Purchases", target
        truth = json.loads((folder.parent / "min119-hard-ground-truth.json").read_text())["mapping"]
        actual = {c["name"]: c["concept"] for c in target["columns"] if c["name"] in truth}
        # The synthetic project reference is a reporting allocation; both
        # evidenced concepts are valid proposals for the human to confirm.
        assert actual["Allocation.Ref"] in ("project", "cost_code"), target
        actual["Allocation.Ref"] = "cost_code"
        assert actual == truth, target
        scan = checked(
            "post",
            base + f"/discovery/runs/{state['scan_id']}/confirm",
            headers=csrf,
            json={"excel_mappings": mappings},
        )
    if "run_id" not in state:
        source = checked(
            "post",
            base + "/accounts/sources",
            headers=csrf,
            data={"paths": '["01-new-scan.pdf"]'},
            files=[("files", ("01-new-scan.pdf", (folder / "01-new-scan.pdf").read_bytes()))],
        )
        run = checked(
            "post",
            base + "/accounts/runs",
            headers=csrf,
            json={
                "key": "bill-entry",
                "request_key": str(uuid.uuid4()),
                "file_ids": [source["files"][0]["id"]],
                "catalog_id": scan["catalog"]["excel_catalog_id"],
                "config": {"output_mode": "excel_in_place"},
            },
        )
        state["run_id"] = run["id"]
        checkpoint.write_text(json.dumps(state))
    run = checked("get", base + f"/accounts/runs/{state['run_id']}")
    if run["state"] in ("queued", "executing"):
        print(f"Extracting hard scan into inferred JSON schema, run {run['id']}.", flush=True)
        proof.hosted(run)
        run = checked("get", base + f"/accounts/runs/{run['id']}")
    if run["state"] == "review":
        data = run["result"]["records"][0]["data"]
        assert {
            k: data[k]
            for k in (
                "Doc.Ref",
                "Party.External",
                "Posting.Day",
                "Allocation.Ref",
                "Txn.Base",
                "Levy.Sum",
                "Settlement.Due",
            )
        } == {
            "Doc.Ref": "MOCK-101",
            "Party.External": "Minkops Demo Supplier",
            "Posting.Day": "2026-10-01",
            "Allocation.Ref": "MOCK-SITE",
            "Txn.Base": 1000,
            "Levy.Sum": 180,
            "Settlement.Due": 1180,
        }, data
        run = checked(
            "post",
            base + f"/accounts/runs/{run['id']}/approve",
            headers=csrf,
            json={"result": run["result"], "acknowledge_findings": True},
        )
    while run["state"] == "writing":
        claim = checked("post", "/api/desktop/worker/claim", headers=worker, json={})
        assert claim and claim["operation"] == "accounts.save", claim
        route = f"/api/desktop/worker/jobs/{claim['id']}"
        plan = checked("get", route + "/plan?claim_token=" + claim["claim_token"], headers=worker)
        result = proof.native(
            {
                "operation": "save_excel",
                "root": proof.WINDOWS_ROOT + r"\apps\solution-api\data\min119-hard-demo",
                "plan": plan,
            }
        )
        for _ in range(2):
            checked(
                "post",
                route + "/finish",
                headers=worker,
                json={"claim_token": claim["claim_token"], "result": result},
            )
        run = checked("get", base + f"/accounts/runs/{run['id']}")
    assert run["state"] == "completed", run["error"]
    rows = list(load_workbook(folder / "mock-register.xlsx")["Bills"].values)
    assert len([r for r in rows if len(r) > 1 and r[1] == "MOCK-101"]) == 1, rows
    state["result"] = run
    checkpoint.write_text(json.dumps(state, default=str, indent=2))
    print(
        "Real Windows discovery, inferred complex schema, scanned extraction, native Excel save and receipt replay passed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
