"""Previewed batch consent over server-derived company/code/subject groups.

One locked transaction validates the whole cohort, audits every member and
queues one write approval or supplier job. A deterministic snapshot token makes
retries idempotent and rejects stale counts before any consequential work.
"""
import copy
import hashlib
import json

from psycopg.types.json import Jsonb

from minkops_platform import attention
from minkops_platform.errors import ServiceError
from minkops_platform.run_controls import require_active

from .bill_decisions import allowed_actions
from .client_context import select_target
from .repository import public_run, run_for

BULK_ACTIONS = ("supplier", "retry_save", "nothing", "retry")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def proposal_identity(record):
    return _digest({key: record.get(key) for key in ("source_file_id", "company_guid", "data", "tax_allocations", "operation")})


def subject_for(run, record):
    """No fuzzy grouping and no subject guessed from a diagnostic sentence."""
    if not isinstance(record, dict):
        return None
    codes = record.get("exception_codes") or [record.get("code")]
    code = record.get("save_hold_code") if record.get("save_hold") else codes[0] if len(codes) == 1 else None
    scope = run["config"].get("tally_target")
    if not scope or not code:
        return None
    try:
        selected = select_target(record, scope)
        guid = selected["references"]["company_guid"]
    except (ValueError, KeyError, TypeError):
        return None
    subject = {"company_guid": guid, "kind": code}
    if code == "supplier_missing":
        vendor = " ".join(str(record.get("data", {}).get("vendor") or "").split())
        if not vendor:
            return None
        gstin = str((record.get("supplier_details") or {}).get("gstin") or "").strip().upper()
        subject.update(vendor=vendor.casefold(), gstin=gstin)
        description = f"{selected['company']} · {vendor}" + (f" · {gstin}" if gstin else "")
    elif record.get("save_hold") or code in ("date_before_books", "voucher_type_unresolved"):
        description = f"{selected['company']} · {code.replace('_', ' ')}"
    else:
        # Ambiguous suppliers/ledger pairs need a future typed master subject.
        return None
    return code, subject, description


def members(run):
    result = run.get("result") or {}
    records = result.get("records", [])
    proposed = {r["source_file_id"] for r in records}
    return [(index, record) for index, record in enumerate(records)] + [
        (None, issue) for issue in result.get("unresolved", []) if issue["source_file_id"] not in proposed]


def options(run):
    """Linear grouping pass for public controls; eligibility still rechecked on POST."""
    groups, by_member = {}, {}
    for index, record in members(run):
        subject = subject_for(run, record)
        if not subject:
            continue
        code, value, _ = subject
        for action in allowed_actions(run, record):
            if action in BULK_ACTIONS:
                key = (action, code, _digest(value))
                groups.setdefault(key, []).append((index, record["source_file_id"]))
    for (action, _, _), cohort in groups.items():
        if len(cohort) > 1:
            for member in cohort:
                by_member.setdefault(member, {})[action] = len(cohort)
    return by_member


def _owned(connection, tenant, user, run_id):
    run = run_for(connection, tenant["id"], run_id, True)
    if run["workflow_key"] != "bill-entry":
        raise ServiceError("not_found", "Bill run not found.")
    if run["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Only this run's operator can authorize bulk decisions.")
    require_active(connection, tenant["id"], run["task_id"])
    return run


def _preview(run, file_id, action, proposal):
    from .attention import _proposal, issue_record
    if run["state"] != "review":
        raise ServiceError("conflict", "This run is still saving or rechecking bills.")
    if action not in BULK_ACTIONS:
        raise ServiceError("invalid", "This action has no supported bulk subject.")
    index = _proposal(run, file_id, proposal)
    issue = next((i for i in run["result"].get("unresolved", []) if i["source_file_id"] == file_id), None)
    trigger = run["result"]["records"][index] if index is not None else issue_record({"records": []}, issue) if issue else None
    subject = subject_for(run, trigger) if trigger else None
    if not subject or action not in allowed_actions(run, trigger):
        raise ServiceError("invalid", "This action has no supported bulk subject.")
    code, value, description = subject
    cohort = [(i, r) for i, r in members(run) if subject_for(run, r) is not None
              and subject_for(run, r)[:2] == subject[:2] and action in allowed_actions(run, r)]
    if len(cohort) < 2:
        raise ServiceError("conflict", "No other open bills share this decision's subject.")
    token = _digest([str(run["id"]), action, code, value, run["updated_at"],
                     [(i, proposal_identity(r), r.get("status")) for i, r in cohort]])
    return {"count": len(cohort), "description": description, "code": code, "subject": value,
            "preview_token": token}, cohort, trigger


def preview(connection, tenant, user, run_id, file_id, action, proposal=None):
    return _preview(_owned(connection, tenant, user, run_id), file_id, action, proposal)[0]


def apply(connection, tenant, user, run_id, file_id, action, proposal, preview_token):
    from .attention import decide, flag
    from .tally_writes import complete_run, defer_input
    from .service import approve_run

    run = _owned(connection, tenant, user, run_id)
    # The audit and application commit atomically. An existing token is a
    # receipt, including while its native saves are still in flight.
    replay = connection.execute("""SELECT 1 FROM attention_events WHERE tenant_id=%s AND actor_id=%s
        AND action='bulk_decision' AND detail->>'run_id'=%s AND detail->>'preview_token'=%s
        AND detail->>'action'=%s AND detail->>'trigger_file_id'=%s LIMIT 1""",
        (tenant["id"], user["id"], str(run_id), preview_token, action, file_id)).fetchone()
    if replay:
        return public_run(connection, run)
    view, cohort, trigger = _preview(run, file_id, action, proposal)
    if preview_token != view["preview_token"]:
        raise ServiceError("conflict", "The similar bills changed. Preview the current count before confirming.")
    kind = "supplier" if action == "supplier" else "bill"
    trigger_item = flag(connection, run, trigger, kind=kind, actor=user["id"])
    for index, record in cohort:
        item = flag(connection, run, record, kind=kind, actor=user["id"])
        attention.audit(connection, item, user["id"], "bulk_decision", f"{action} authorized for {view['count']} similar bills.", detail={
            "version": 1, "run_id": str(run_id), "company_guid": view["subject"]["company_guid"],
            "code": view["code"], "subject": view["subject"], "action": action, "actor_id": str(user["id"]),
            "source_item_id": str(item["id"]), "trigger_item_id": str(trigger_item["id"]),
            "trigger_file_id": file_id, "trigger_proposal": proposal, "count": view["count"],
            "member_key": f"{record['source_file_id']}:{index}", "record_index": index,
            "preview_token": preview_token,
            "decision_key": _digest([str(run_id), view["code"], view["subject"], action]),
        })
    indices = {i for i, _ in cohort if i is not None}
    if action == "supplier":
        decide(connection, tenant, user, run_id, file_id, action, proposal)
        consent = [{"record_index": i, "source_file_id": r["source_file_id"], "identity": proposal_identity(r)} for i, r in cohort]
        connection.execute("UPDATE attention_items SET target=target || %s WHERE tenant_id=%s AND id=%s",
            (Jsonb({"authorized_proposals": consent}), tenant["id"], trigger_item["id"]))
    elif action == "retry":
        from .batch import recheck_many
        recheck_many(connection, tenant, user, run, list(dict.fromkeys(r["source_file_id"] for _, r in cohort)))
    else:
        result = copy.deepcopy(run["result"])
        for index, record in enumerate(result["records"]):
            if index in indices:
                if action == "nothing":
                    record.update(status="rejected", decision="reject")
                else:
                    reason = record.pop("save_hold")
                    record["findings"] = [f for f in record["findings"] if f != reason]
                    record["decision"] = "approve"
            elif record.get("status") not in ("saved", "duplicate", "rejected", "writing"):
                record["decision"] = "hold"
        for index, record in cohort:
            if index is None:
                defer_input(result, record["source_file_id"])
                connection.execute("UPDATE account_runs SET config=config || '{\"superseded\":true}'::jsonb WHERE tenant_id=%s AND parent_run_id=%s AND file_ids @> %s",
                    (tenant["id"], run_id, Jsonb([record["source_file_id"]])))
        if action == "nothing":
            complete_run(connection, run, result)
        else:
            connection.execute("UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s", (Jsonb(result), tenant["id"], run_id))
            approve_run(connection, tenant, user, run_id, {"result": result, "acknowledge_findings": True})
    return public_run(connection, run_for(connection, tenant["id"], run_id))
