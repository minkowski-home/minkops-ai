"""Accounts evidence and one-click decisions over shared attention state."""
import copy
import base64
import hashlib
import json
from decimal import Decimal, InvalidOperation
from psycopg.types.json import Jsonb
from minkops_platform import attention
from minkops_platform.errors import ServiceError
from .repository import run_for, public_run


def target_for(connection, run, record):
    scope = run["config"].get("tally_target")
    if not scope:
        mapping = next((s for s in run["config"]["catalog_snapshot"]["sheets"]
                        if s["file_id"] == record.get("destination_file_id") and s["sheet"] == record.get("sheet")
                        and s.get("table") == record.get("table")), None)
        if not mapping:
            return {}
        file = connection.execute("""SELECT f.path,f.source_id,b.device_id FROM account_files f
            JOIN desktop_source_bindings b ON b.source_id=f.source_id AND b.tenant_id=f.tenant_id
            WHERE f.tenant_id=%s AND f.id=%s""", (run["tenant_id"], mapping["file_id"])).fetchone()
        if not file:
            return {}
        return {"tool": "excel", "device_id": str(file["device_id"]), "source_id": str(file["source_id"]),
                "path": file["path"], "mapping": mapping,
                "keys": {k: record["data"].get(k) for k in mapping["key_columns"]},
                "run_id": str(run["id"]), "file_id": record["source_file_id"], "baseline": None}
    from .client_context import select_target
    try:
        selected = select_target(record, scope)
    except ValueError:
        return {}
    return {"tool": "tally", "device_id": scope["device_id"], "company": selected["company"],
            "company_guid": selected["references"]["company_guid"], "port": selected["port"],
            "vendor": record["data"].get("vendor"), "invoice_number": record["data"].get("invoice_number"),
            "run_id": str(run["id"]), "file_id": record["source_file_id"],
            "baseline": record.get("current")}


def flag(connection, run, record, *, title=None, kind="bill", actor=None):
    file_id = record["source_file_id"]
    name = next((f["path"] for f in run["config"].get("file_provenance", []) if f["id"] == file_id), file_id)
    return attention.record(connection, run, f"bill:{run['id']}:{file_id}:{kind}", name,
        title or attention.label(" ".join(record.get("findings", []))), kind=kind,
        target=target_for(connection, run, record), actor=actor)


def decide(connection, tenant, user, run_id, file_id, action):
    from .service import approve_run
    from .batch import resolve_bill
    run = run_for(connection, tenant["id"], run_id, True)
    if run["actor_id"] != user["id"] or run["state"] != "review":
        raise ServiceError("forbidden", "Only this run's operator can authorize bill writes.")
    original = next((r for r in run["result"]["records"] if r["source_file_id"] == file_id), None)
    issue = next((i for i in run["result"].get("unresolved", []) if i["source_file_id"] == file_id), None)
    if not original and not issue:
        raise ServiceError("invalid", "Bill not awaiting a decision.")
    record = original or {"source_file_id": file_id, "data": {}, "findings": [issue["reason"]]}
    if record.get("status") in ("saved", "duplicate", "rejected", "writing"):
        raise ServiceError("conflict", "Bill already handled.")
    if action == "retry":
        return resolve_bill(connection, tenant, user, run_id, file_id, "", False)
    if action == "nothing":
        item = flag(connection, run, record, actor=user["id"])
        attention.audit(connection, item, user["id"], "deferred", "No write. Manual handling required.")
        if issue:
            if original:
                original.update(decision="reject", status="rejected")
                connection.execute("UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(run["result"]), run["id"]))
            return resolve_bill(connection, tenant, user, run_id, file_id, "", True)
        result = copy.deepcopy(run["result"])
        for row in result["records"]:
            if row["source_file_id"] == file_id:
                row.update(decision="reject", status="rejected")
        from .tally_writes import complete_run
        complete_run(connection, run, result)
        return public_run(connection, run_for(connection, tenant["id"], run_id))
    if not original:
        raise ServiceError("invalid", "No supported proposal. Handle this bill in the original system.")
    scope = run["config"].get("tally_target")
    from .client_context import select_target
    from .bills import validate_tally
    try:
        selected = select_target(record, scope) if scope else None
        if action == "supplier":
            if not selected or record["data"].get("tax") != 0 or record["data"].get("vendor") in selected["ledgers"]:
                raise ValueError("Supplier creation needs a supported non-tax bill and a new supplier.")
            vendor = record["data"]["vendor"]
            if not any(e.get("field") == "vendor" and e.get("quote", "").strip() for e in record["evidence"]):
                raise ValueError("Supplier name needs bill evidence.")
            prospective = {**selected, "ledgers": [*selected["ledgers"], vendor]}
            validate_tally(record["data"], prospective)
            item = flag(connection, run, record, title="Missing supplier", kind="supplier", actor=user["id"])
            attention.enqueue(connection, item, user, "attention.supplier")
            return public_run(connection, run)
        if action != "guess":
            raise ValueError("Unsupported bill decision.")
        if selected:
            validate_tally(record["data"], selected)
        if record.get("findings"):
            flag(connection, run, record, title="Review written bill", kind="review", actor=user["id"])
        # One click authorizes the observed correction; no operation or values
        # are editable by the renderer. Native compare-and-readback still applies.
        if record.get("current") or record.get("current_excel"):
            record["operation"] = "update"
            if record.get("current_excel"):
                record["expected_excel"] = record["current_excel"]
            connection.execute("UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(run["result"]), run["id"]))
        result = copy.deepcopy(run["result"])
        result["unresolved"] = [i for i in result.get("unresolved", []) if i["source_file_id"] != file_id]
        for row in result["records"]:
            row["decision"] = "approve" if row["source_file_id"] == file_id else "hold"
        return approve_run(connection, tenant, user, run_id, {"result": result, "acknowledge_findings": True})
    except (ValueError, KeyError, TypeError) as error:
        raise ServiceError("invalid", "No supported write. Use Do nothing.") from error


def check_observation(item, observation):
    target = item["target"]
    if target.get("tool") == "excel":
        from minkops_connectors.excel import sheet_records, open_workbook, mapped_columns
        from .catalog import validate_data
        try:
            content = base64.b64decode(observation["content"], validate=True)
            if len(content) > 4_000_000:
                raise ValueError("Workbook too large.")
            rows = [r for r in sheet_records(content, target["mapping"])
                    if all(str(r["data"].get(k)).strip().casefold() == str(v).strip().casefold() for k,v in target["keys"].items())]
            if len(rows) != 1:
                return {"valid": False}
            sheet = open_workbook(content)[target['mapping']['sheet']]
            columns = mapped_columns(sheet,target['mapping'])
            # Formula text is not a numeric readback. Optional calculated cells
            # are excluded; required business values must still be observable.
            for column in target['mapping']['columns']:
                if not column['required'] and sheet.cell(rows[0]['row'],columns[column['name']]).data_type == 'f':
                    rows[0]['data'][column['name']] = None
            validate_data(target["mapping"], rows[0]["data"])
            return {"valid": True, "current": {"guid": json.dumps(target["keys"], sort_keys=True),
                "fingerprint": hashlib.sha256(json.dumps(rows[0]["data"], sort_keys=True, default=str).encode()).hexdigest()}}
        except (ValueError, KeyError, TypeError):
            return {"valid": False}
    if not isinstance(observation, dict) or observation.get("company_guid") != target.get("company_guid"):
        raise ServiceError("invalid", "Destination identity changed.")
    # Native observations are data. The server independently validates the
    # business identity and balanced accounting entries before completion.
    current = observation.get("current")
    valid = False
    if current:
        try:
            entries = current["entries"]
            amounts = [Decimal(str(e["amount"])) for e in entries]
            valid = (current["invoice_number"] == target["invoice_number"]
                and current["vendor"] == target["vendor"] and bool(current.get("guid"))
                and bool(current.get("fingerprint")) and len(amounts) >= 2
                and all(v.is_finite() for v in amounts) and sum(amounts) == 0
                and any(e["ledger"] == target["vendor"] and Decimal(str(e["amount"])) > 0 for e in entries))
        except (KeyError, TypeError, InvalidOperation):
            valid = False
    masters = observation.get("ledgers", [])
    if not isinstance(masters, list) or any(not isinstance(m, dict) for m in masters):
        raise ServiceError("invalid", "Invalid native masters.")
    names = [m.get("@_NAME", m.get("NAME")) for m in masters]
    return {"valid": valid if item["kind"] != "supplier" else target["vendor"] in names,
            "ledgers": names, "masters": masters, "current": current}


def excel_baseline(connection, run, record, content):
    item = connection.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s AND status='pending' FOR UPDATE",
        (run["tenant_id"], f"bill:{run['id']}:{record['source_file_id']}:review")).fetchone()
    if item and item["target"]:
        observation = check_observation(item, {"content": base64.b64encode(content).decode()})
        if observation["valid"]:
            connection.execute("UPDATE attention_items SET target=jsonb_set(target,'{baseline}',%s) WHERE id=%s",
                               (Jsonb(observation["current"]), item["id"]))


def written(connection, run, record):
    """A verified save resolves the blocked-write event, never the review event."""
    item = connection.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s AND status='pending' FOR UPDATE",
        (run["tenant_id"], f"bill:{run['id']}:{record['source_file_id']}:bill")).fetchone()
    if item:
        connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                           (run['actor_id'], item['id']))
        attention.audit(connection, item, run['actor_id'], 'verified_done', 'Bill save verified. Separate review remains pending.')


def supplier_created(connection, item, job, observation):
    if not observation["valid"]:
        return
    target = item["target"]
    run = run_for(connection, item["tenant_id"], target["run_id"], True)
    if run["state"] != "review":
        return
    from .client_context import select_target
    from .tally_writes import prepare, complete_run
    result = copy.deepcopy(run["result"])
    record = next(r for r in result["records"] if r["source_file_id"] == target["file_id"])
    if item["status"] == "done" or record.get("status") in ("saved", "duplicate", "rejected", "writing"):
        return
    selected = select_target(record, run["config"]["tally_target"])
    master = next(m for m in observation["masters"] if m.get("@_NAME", m.get("NAME")) == target["vendor"])
    if master.get("PARENT") != "Sundry Creditors" or not master.get("GUID"):
        raise ServiceError("invalid", "Supplier definition needs review.")
    selected["ledgers"] = list(dict.fromkeys([*selected["ledgers"], target["vendor"]]))
    selected["references"]["ledgers"][target["vendor"]] = {k: master.get(k) for k in ("GUID", "PARENT", "ALTERID")}
    record["decision"] = "approve"
    result["unresolved"] = [i for i in result.get("unresolved", []) if i["source_file_id"] != target["file_id"]]
    for row in result["records"]:
        if row is not record and row.get("status") not in ("saved", "duplicate", "writing", "rejected"):
            row["decision"] = "hold"
    connection.execute("UPDATE account_runs SET config=%s WHERE id=%s", (Jsonb(run["config"]), run["id"]))
    # The native-created master is scoped to this continuation. Other runs keep
    # their confirmed snapshots and must refresh discovery to see the new master.
    prepare(connection, run, result, approved=True)
    complete_run(connection, run, result)
    attention.audit(connection, item, job["actor_id"], "continued", "Supplier verified. Bill save queued.")
