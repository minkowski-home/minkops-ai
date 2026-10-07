"""Opt-in real hosted extraction + Windows/Tally proof for synthetic mock data.

Uses a dedicated database and never passes server model credentials to the
Windows adapter process. Ground truth is assertions, never agent context.
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import uuid
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from minkops_api.main import app
from minkops_platform.accounts.batch import reconcile_once
from minkops_platform.accounts.run_store import AccountsRunStore
from minkops_platform.accounts.worker import process
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
COMPANY = os.environ["MINKOPS_TALLY_TEST_COMPANY"]
DATABASE = os.environ["DATABASE_URL"]
if not DATABASE.endswith("/minkops_min119_live"):
    raise RuntimeError("Use the dedicated minkops_min119_live database.")
load_dotenv(ROOT / "apps/solution-api/.env")
NODE = os.environ.get("MINKOPS_WINDOWS_NODE", "node.exe")
WINDOWS_ROOT = (
    os.environ.get("MINKOPS_WINDOWS_ROOT")
    or subprocess.check_output(["wslpath", "-w", str(ROOT)], text=True).strip()
)


def native(payload):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("OPENAI_")}
    reply = subprocess.run(
        [NODE, WINDOWS_ROOT + r"\scripts\min119-native.mjs"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env=environment,
        timeout=180,
    )
    return json.loads(reply.stdout)


client = TestClient(app)


def checked(method, path, **kwargs):
    response = getattr(client, method)(path, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"{path}: {response.status_code}: {response.text[:500]}")
    return response.json()


def hosted(run):
    with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
        row = connection.execute("SELECT * FROM account_runs WHERE id=%s", (run["id"],)).fetchone()
        assert row["config"]["execution_snapshot"]["execution"]["model"] == "gpt-6-luna"
        try:
            process(connection, row)
        except Exception as error:
            connection.rollback()
            AccountsRunStore().fail(connection, row, f"Live verification: {type(error).__name__}")
            connection.commit()
            print(f"Bill {row['id']} needs attention ({type(error).__name__}).", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", help="Reconcile saved sessions for an existing proof batch.")
    args = parser.parse_args()
    checked(
        "post",
        "/api/auth/login",
        json={"email": "demo@example.com", "password": "long test password 123!"},
    )
    csrf = {"x-csrf-token": checked("get", "/api/auth/me")["csrf_token"]}
    base = "/api/tenants/mock-tenant/accounts"
    discovery = "/api/tenants/mock-tenant/discovery"
    installation_id = str(uuid.uuid4())
    if args.resume:
        with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
            run = connection.execute(
                "SELECT * FROM account_runs WHERE id=%s", (args.resume,)
            ).fetchone()
            installation_id = connection.execute(
                "SELECT installation_id FROM desktop_devices WHERE id=%s",
                (run["config"]["tally_target"]["device_id"],),
            ).fetchone()["installation_id"]
            installation_id = str(installation_id)
    device = checked(
        "post",
        "/api/tenants/mock-tenant/desktop/devices",
        headers=csrf,
        json={"name": "MIN119 Windows proof", "installation_id": installation_id},
    )
    worker = {"Authorization": "Bearer " + device["credential"]}
    folder = ROOT / "apps/solution-api/data/min119-hard-demo"
    if not args.resume:
        run = launch_batch(csrf, base, discovery, device, worker, folder)
    with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
        children = connection.execute(
            "SELECT * FROM account_runs WHERE parent_run_id=%s AND state IN ('queued','executing')",
            (run["id"],),
        ).fetchall()
    print(
        f"Processing {len(children)} pending independent gpt-6-luna turns (two concurrent).",
        flush=True,
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(hosted, children))
    reconcile_once(DATABASE)
    verify_and_save(csrf, base, worker, folder, run)


def launch_batch(csrf, base, discovery, device, worker, folder):
    config = {
        "company": COMPANY,
        "port": 9000,
        "categories": ["company", "ledgers", "voucher_types"],
    }
    scan = checked(
        "post",
        discovery + "/runs",
        headers=csrf,
        json={
            "device_id": device["id"],
            "request_key": str(uuid.uuid4()),
            "config": {"depth": "business_mappings", "excel_source_ids": [], "tally": config},
        },
    )
    claim = checked("post", "/api/desktop/worker/claim", headers=worker, json={})
    snapshot = native({"operation": "discover", "config": {**config, "depth": "business_mappings"}})
    checked(
        "post",
        f"/api/desktop/worker/jobs/{claim['id']}/finish",
        headers=worker,
        json={
            "claim_token": claim["claim_token"],
            "result": {
                "sources": [
                    {"key": "tally", "tool": "tally", "status": "ready", "snapshot": snapshot}
                ]
            },
        },
    )
    checked("post", discovery + f"/runs/{scan['id']}/confirm", headers=csrf, json={})
    paths = ["01-new-scan.pdf", "02-new-scan.pdf", "03-backfill-scan.pdf", "05-unreadable.png"]
    source = checked(
        "post",
        base + "/sources",
        headers=csrf,
        data={"paths": json.dumps(paths)},
        files=[("files", (p, (folder / p).read_bytes())) for p in paths],
    )
    run = checked(
        "post",
        base + "/runs",
        headers=csrf,
        json={
            "key": "bill-entry",
            "request_key": str(uuid.uuid4()),
            "file_ids": [f["id"] for f in source["files"]],
            "catalog_id": None,
            "config": {"output_mode": "tally_in_place", "discovery_id": scan["id"]},
        },
    )
    print(
        f"Proof batch {run['id']} persisted; use --resume with this ID after interruption.",
        flush=True,
    )
    return run


def verify_and_save(csrf, base, worker, folder, run):
    loaded = checked("get", base + f"/runs/{run['id']}")
    (folder.parent / "min119-live-result.json").write_text(
        json.dumps(loaded, default=str, indent=2)
    )
    expected = {
        "MOCK-101": (1000, 180, 1180),
        "MOCK-102": (2000, 360, 2360),
        "MOCK-099": (500, 90, 590),
    }
    for record in loaded["result"]["records"]:
        data = record["data"]
        assert data["vendor"] == "Minkops Demo Supplier", data
        assert data["date"] == "2026-10-01", data
        assert (data["subtotal"], data["tax"], data["total"]) == expected.pop(
            data["invoice_number"]
        ), data
    assert not expected, expected
    assert len(loaded["result"]["unresolved"]) == 1, loaded["result"]
    approved = checked(
        "post",
        base + f"/runs/{run['id']}/approve",
        headers=csrf,
        json={"result": loaded["result"], "acknowledge_findings": True},
    )
    assert len(approved["tally_writes"]) == 3
    for _ in range(3):
        claim = checked("post", "/api/desktop/worker/claim", headers=worker, json={})
        route = f"/api/desktop/worker/jobs/{claim['id']}"
        plan = checked("get", route + "/plan?claim_token=" + claim["claim_token"], headers=worker)
        receipt = {
            "claim_token": claim["claim_token"],
            "result": native({"operation": "save", "plan": plan}),
        }
        checked("post", route + "/finish", headers=worker, json=receipt)
        checked("post", route + "/finish", headers=worker, json=receipt)
    saved = checked("get", base + f"/runs/{run['id']}")
    assert saved["state"] == "review" and all(w["verified_at"] for w in saved["tally_writes"]), (
        saved
    )
    (folder.parent / "min119-live-result.json").write_text(json.dumps(saved, default=str, indent=2))
    print(
        "Complex scan extraction, mapping, arithmetic, isolated unreadable input, native approved Tally writes and receipt replay passed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
