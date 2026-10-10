"""Opt-in paid MIN-124 verification against a dedicated local database and Windows.

Run on WSL after preparing authorised test companies and an Excel-authored
register.xlsx. Evidence/checkpoints remain in ignored data; no model credentials
reach the native bridge. Resume reconciles existing hosted sessions.
"""

import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path

if not __debug__:
    raise RuntimeError("Live verification requires checks; do not run with python -O.")

import psycopg
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
DATABASE = os.environ["DATABASE_URL"]
if not DATABASE.endswith("/minkops_min124_live"):
    raise RuntimeError("Use the dedicated local minkops_min124_live database.")
load_dotenv(ROOT / "apps/solution-api/.env", override=False)
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Configure the existing server OPENAI_API_KEY.")
from minkops_api.main import app
from minkops_platform.accounts.batch import reconcile_once
from minkops_platform.accounts.worker import process
from minkops_platform.accounts.run_store import AccountsRunStore

NATIVE_ROOT = os.environ["MINKOPS_WINDOWS_ROOT"]
NODE = os.environ["MINKOPS_WINDOWS_NODE"]
DATA = Path(os.environ["MINKOPS_LIVE_DATA"])
DATA.mkdir(parents=True, exist_ok=True)
CHECKPOINT = DATA / "checkpoint.json"
state = json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {}
client = TestClient(app)
base = "/api/tenants/mock-tenant"
csrf = {}
worker = {}


def checkpoint():
    CHECKPOINT.write_text(json.dumps(state, default=str, indent=2))


def api(method, path, expected=None, **kwargs):
    response = getattr(client, method)(path, **kwargs)
    if expected is not None:
        assert response.status_code == expected, response.text[:500]
    elif response.status_code >= 400:
        raise RuntimeError(f"{path}: {response.status_code}: {response.text[:500]}")
    return response.json()


def native(payload):
    environment = {k: v for k, v in os.environ.items() if not k.startswith("OPENAI_")}
    response = subprocess.run(
        [NODE, NATIVE_ROOT + r"\scripts\min119-native.mjs"],
        input=json.dumps(payload), text=True, capture_output=True, env=environment, timeout=180,
    )
    if response.returncode:
        raise RuntimeError(response.stderr[-1500:])
    return json.loads(response.stdout)


def hosted(run_id):
    with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
        run = connection.execute("SELECT * FROM account_runs WHERE id=%s", (run_id,)).fetchone()
        assert run["config"]["execution_snapshot"]["execution"]["model"] == "gpt-6-luna"
        if run["state"] in ("queued", "executing"):
            print(f"Hosted gpt-6-luna: {run['workflow_key']} {run_id}", flush=True)
            try:
                process(connection, run)
            except Exception as error:
                connection.rollback()
                AccountsRunStore().fail(connection, run, f"Live verification: {type(error).__name__}: {str(error)[:250]}")
                connection.commit()
                raise
    reconcile_once(DATABASE)


def finish_job(operation, root=None):
    job = api("post", "/api/desktop/worker/claim", headers=worker, json={})
    assert job, "No pending native job"
    route = f"/api/desktop/worker/jobs/{job['id']}"
    plan = (None if operation == "refresh" else
            api("get", route + "/plan?claim_token=" + job["claim_token"], headers=worker))
    try:
        result = native({"operation": operation, "plan": plan, "root": root})
    except Exception as error:
        api("post", route + "/finish", headers=worker,
            json={"claim_token": job["claim_token"], "result": None, "error": str(error)[-300:]})
        raise
    receipt = {"claim_token": job["claim_token"], "result": result}
    api("post", route + "/finish", headers=worker, json=receipt)
    api("post", route + "/finish", headers=worker, json=receipt)
    return result


def discovery(config=None, root=None):
    config = config or {"depth": "client_context", "excel_source_ids": [],
                        "tally": {"port": 9000, "period": {"from": "2026-10-01", "to": "2026-10-02"}}}
    if "discovery_id" not in state:
        scan = api("post", base + "/discovery/runs", headers=csrf, json={
            "device_id": state["device_id"], "request_key": str(uuid.uuid4()),
            "config": config,
        })
        state["discovery_id"] = scan["id"]
        checkpoint()
        finish_job("collect", root)
    path = base + f"/discovery/runs/{state['discovery_id']}"
    scan = api("get", path)
    assert not scan["catalog"]["partial"], scan["catalog"]
    if not scan["ready"]:
        hosted(scan["mapping_run"]["id"])
        scan = api("get", path)
        assert scan["mapping_run"]["state"] == "review", scan["mapping_run"]
        if not config["excel_source_ids"]:
            assert scan["mapping_run"]["result"]["sheets"] == []
        scan = api("post", path + "/confirm", headers=csrf, json={})
    assert scan["ready"] and scan["catalog"]["format_version"] == "2"
    state["catalog"] = scan["catalog"]
    checkpoint()
    native({"operation": "archive", "root": NATIVE_ROOT + r"\evidence\min124\confirmed", "catalog": scan["catalog"]})
    return scan


def invoices(scan):
    import pymupdf as fitz

    if "invoices" not in state:
        suffix = uuid.uuid4().hex[:8]
        state["invoices"] = [
            {"buyer": c["company"], "company_guid": c["company_guid"],
             "invoice": "MIN124-" + suffix, "amount": 101 + i * 101, "path": f"bill-{i}.pdf"}
            for i, c in enumerate(scan["catalog"]["sources"][0]["snapshot"]["companies"])
        ]
        for invoice in state["invoices"]:
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((60, 80), "SYNTHETIC TEST INVOICE - NOT A VALID TAX DOCUMENT", fontsize=12)
            page.insert_text((60, 120), "\n".join([
                "Supplier: MIN124 Shared Supplier", f"Invoice Number: {invoice['invoice']}",
                "Invoice Date: 01 October 2026", f"Bill to / Buyer legal name: {invoice['buyer']}",
                "Description: Materials expense, accounting voucher without inventory/cost allocations",
                "Purchase expense allocation: MIN124 Purchases", f"Subtotal: INR {invoice['amount']}.00",
                "Tax: INR 0.00 (non GST test transaction)", f"Total payable: INR {invoice['amount']}.00",
            ]), fontsize=11)
            doc.save(DATA / invoice["path"])
            doc.close()
        checkpoint()
    return state["invoices"]


def bills(scan, resume_saves=False):
    expected = invoices(scan)
    if "batch_id" not in state:
        source = api("post", base + "/accounts/sources", headers=csrf,
            data={"paths": json.dumps([x["path"] for x in expected])},
            files=[("files", (x["path"], (DATA / x["path"]).read_bytes())) for x in expected])
        run = api("post", base + "/accounts/runs", headers=csrf, json={
            "key": "bill-entry", "request_key": str(uuid.uuid4()),
            "file_ids": [f["id"] for f in source["files"]], "catalog_id": None,
            "config": {"output_mode": "tally_in_place", "discovery_id": scan["id"], "company_mode": "infer"},
        })
        state["batch_id"] = run["id"]
        checkpoint()
    with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
        children = connection.execute("SELECT id FROM account_runs WHERE parent_run_id=%s", (state["batch_id"],)).fetchall()
    for child in children:
        hosted(child["id"])
    path = base + f"/accounts/runs/{state['batch_id']}"
    run = api("get", path)
    (DATA / "bill-review.json").write_text(json.dumps(run, default=str, indent=2))
    assert len(run["result"]["records"]) == len(expected), run["result"]
    assert not run["result"]["unresolved"], run["result"]
    for record in run["result"]["records"]:
        invoice = next(x for x in expected if x["company_guid"] == record["company_guid"])
        assert record["company_evidence"].strip()
        assert record["data"]["invoice_number"] == invoice["invoice"]
        assert record["data"]["vendor"] == "MIN124 Shared Supplier"
        assert record["data"]["purchase_ledger"] == "MIN124 Purchases"
        assert record["data"]["date"] == "2026-10-01"
        assert (record["data"]["subtotal"], record["data"]["tax"], record["data"]["total"]) == (invoice["amount"], 0, invoice["amount"])
    if run["state"] == "review":
        run = api("post", path + "/approve", headers=csrf, json={"result": run["result"], "acknowledge_findings": True})
    if resume_saves:
        for write in run["tally_writes"]:
            if not write["verified_at"]:
                api("post", base + "/desktop/jobs", headers=csrf, json={
                    "device_id": state["device_id"], "request_key": str(uuid.uuid4()),
                    "operation": "tally.save", "input": {"run_id": run["id"], "write_id": write["id"]}})
    while run["state"] == "writing":
        finish_job("save")
        run = api("get", path)
    assert run["state"] == "completed", run
    assert all(w["verified_at"] for w in run["tally_writes"])
    for invoice in expected:
        matches = [v for v in native({"operation": "read", "plan": {"company": invoice["buyer"]}})
                   if v["invoice_number"] == invoice["invoice"]]
        assert len(matches) == 1 and matches[0]["vendor"] == "MIN124 Shared Supplier"
    (DATA / "bill-receipts.json").write_text(json.dumps(run, default=str, indent=2))
    print("Live confirmed discovery, inferred mixed-company batch, reviewed native writes and replay passed.", flush=True)


def connect():
    global csrf, worker
    api("post", "/api/auth/login", json={"email": "demo@example.com", "password": "long test password 123!"})
    csrf = {"x-csrf-token": api("get", "/api/auth/me")["csrf_token"]}
    state.setdefault("installation_id", str(uuid.uuid4()))
    device = api("post", base + "/desktop/devices", headers=csrf,
                 json={"name": "MIN124 live proof", "installation_id": state["installation_id"]})
    state["device_id"] = device["id"]
    worker = {"Authorization": "Bearer " + device["credential"]}
    checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-only", action="store_true")
    parser.add_argument("--resume-saves", action="store_true", help="Explicitly reconcile interrupted approved saves.")
    args = parser.parse_args()
    connect()
    scan = discovery()
    if not args.discovery_only:
        bills(scan, args.resume_saves)


if __name__ == "__main__":
    main()
