"""Accounts evidence and one-click decisions over shared attention state."""
import copy
from decimal import Decimal, InvalidOperation

from psycopg.types.json import Jsonb

from minkops_platform import attention
from minkops_platform.errors import ServiceError
from minkops_platform.runtime.assets import config_json

from .repository import public_run, run_for


def target_for(connection, run, record):
    # Stop can race the interval between provider-result persistence and bill
    # validation. Preserve the source link without trusting raw document values.
    data = record.get("data") or {}
    scope = run["config"].get("tally_target")
    if not scope:
        return {}
    from .client_context import select_target
    try:
        selected = select_target(record, scope)
    except ValueError:
        return {}
    return {"tool": "tally", "device_id": scope["device_id"], "company": selected["company"],
            "company_guid": selected["references"]["company_guid"], "port": selected["port"],
            "vendor": data.get("vendor"), "invoice_number": data.get("invoice_number"),
            "date": data.get("date"),
            "run_id": str(run["id"]), "file_id": record["source_file_id"],
            "baseline": record.get("current")}


def exception_label(record):
    """Coded exceptions name themselves; older free-text findings use the keyword fallback."""
    from .checks import EXCEPTION_LABELS
    codes = record.get("exception_codes") or []
    return EXCEPTION_LABELS[codes[0]] if codes else attention.label(" ".join(record.get("findings", [])))


def issue_record(result, issue):
    """The proposal for an unresolved input, or a placeholder carrying its reason."""
    return next((r for r in result["records"] if r["source_file_id"] == issue["source_file_id"]),
                {"source_file_id": issue["source_file_id"], "data": {}, "findings": [issue["reason"]],
                 "exception_codes": [issue["code"]] if issue.get("code") else []})


def flag(connection, run, record, *, title=None, kind="bill", actor=None, reopen=False):
    """Attention for one input file; `reopen` only for a new hold event (see attention.record)."""
    file_id = record["source_file_id"]
    name = next((f["path"] for f in run["config"].get("file_provenance", []) if f["id"] == file_id), file_id)
    from .bill_review import reason_sentence
    target = {**target_for(connection, run, record), "reason": reason_sentence(record, title=title)}
    return attention.record(connection, run, f"bill:{run['id']}:{file_id}:{kind}", name,
        title or exception_label(record), kind=kind,
        target=target, actor=actor, reopen=reopen)


def stopped(connection, run, actor):
    """Retain both proposals and unresolved inputs when automation is stopped.

    A batch stopped before aggregation holds its read bills only in children,
    so their outcomes are included for inputs the parent has not combined yet.
    Inputs that were never read have no proposal and open no item.
    """
    results = [run.get("result") or {}]
    if run.get("config", {}).get("batch"):
        results += [child["result"] for child in connection.execute(
            """SELECT result FROM account_runs WHERE tenant_id=%s AND parent_run_id=%s AND result IS NOT NULL
            AND NOT coalesce((config->>'superseded')::boolean,false) ORDER BY file_ids->>0""",
            (run["tenant_id"], run["id"]))]
    records = {}
    for result in results:
        # The parent's combined outcome comes first and wins for each input.
        for record in result.get("records", []):
            records.setdefault(record["source_file_id"], record)
        for issue in result.get("unresolved", []):
            records.setdefault(issue["source_file_id"], issue_record({"records": []}, issue))
    for record in records.values():
        if record.get("status") not in ("saved", "duplicate", "rejected"):
            item = flag(connection, run, record, title="Run stopped", actor=actor)
            attention.audit(connection, item, actor, "stopped",
                            "Remaining automation stopped. Verify the original destination before further action.")


def _proposal(run, file_id, proposal):
    """The one proposal a decision applies to; an input file can hold several bills.

    Without an explicit index, only a file with a single undecided proposal is
    unambiguous. Inputs without any proposal return None.
    """
    from .tally_writes import SETTLED
    records = run["result"]["records"]
    indexes = [i for i, r in enumerate(records) if r["source_file_id"] == file_id]
    if proposal is not None:
        if proposal not in indexes:
            raise ServiceError("invalid", "Bill not awaiting a decision.")
        return proposal
    pending = [i for i in indexes if records[i].get("status") not in SETTLED]
    if len(pending) > 1:
        raise ServiceError("invalid", "Choose which bill in this file to decide.")
    return (pending or indexes or [None])[0]


def decide(connection, tenant, user, run_id, file_id, action, proposal=None):
    from .batch import resolve_bill
    from .service import approve_run
    run = run_for(connection, tenant["id"], run_id, True)
    from minkops_platform.run_controls import require_active
    require_active(connection, tenant["id"], run["task_id"])
    if run["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Only this run's operator can authorize bill writes.")
    if run["state"] != "review":
        # Saving or rechecking: decisions resume when the run returns to review.
        raise ServiceError("conflict", "This run is still saving or rechecking bills. Decide once it is ready.")
    index = _proposal(run, file_id, proposal)
    original = None if index is None else run["result"]["records"][index]
    issue = next((i for i in run["result"].get("unresolved", []) if i["source_file_id"] == file_id), None)
    if not original and not issue:
        raise ServiceError("invalid", "Bill not awaiting a decision.")
    record = original or issue_record({"records": []}, issue)
    if record.get("status") in ("saved", "duplicate", "rejected", "writing"):
        raise ServiceError("conflict", "Bill already handled.")
    from .bill_decisions import allowed_actions
    if action not in allowed_actions(run, record):
        raise ServiceError("invalid", "This decision is unavailable for this bill. Use an offered action or handle it in the original system.")
    if action == "retry":
        return resolve_bill(connection, tenant, user, run_id, file_id, False)
    if action == "retry_save":
        return _retry_save(connection, tenant, user, run, index)
    if record.get("save_hold") and action in ("guess", "supplier"):
        raise ServiceError("invalid", "Fix the destination, then use Retry save.")
    if action == "nothing":
        item = flag(connection, run, record, actor=user["id"])
        attention.audit(connection, item, user["id"], "deferred", "No write. Manual handling required.")
        if not original:
            # An input without any proposal is deferred as a whole.
            return resolve_bill(connection, tenant, user, run_id, file_id, True)
        # Only this proposal is final; the input settles once all of its bills do.
        result = copy.deepcopy(run["result"])
        result["records"][index].update(decision="reject", status="rejected")
        from .tally_writes import complete_run
        complete_run(connection, run, result)
        return public_run(connection, run_for(connection, tenant["id"], run_id))
    if not original:
        raise ServiceError("invalid", "No supported proposal. Handle this bill in the original system.")
    scope = run["config"].get("tally_target")
    from .bill_decisions import supported_write
    from .client_context import select_target
    from .vouchers import resolve
    try:
        selected = select_target(record, scope) if scope else None
        if action == "supplier":
            # Missing names are not evidence of a genuinely new supplier: the
            # proposal must establish one, with evidence, and be otherwise valid.
            if not selected or not supported_write(run, record, supplier=True):
                raise ValueError("Supplier creation needs a supported bill and a positively new supplier.")
            from .vouchers import summary
            record["data"] = summary(record, run["config"])
            from .supplier_gst import creation_plan
            gst_supplier = creation_plan(run, record, selected)
            item = flag(connection, run, record, title="Missing supplier", kind="supplier", actor=user["id"])
            if gst_supplier:
                connection.execute("UPDATE attention_items SET target=target || %s WHERE tenant_id=%s AND id=%s RETURNING *",
                    (Jsonb({"gst_supplier": gst_supplier}), tenant["id"], item["id"]))
            attention.enqueue(connection, item, user, "attention.supplier")
            return public_run(connection, run)
        if action != "guess":
            raise ValueError("Unsupported bill decision.")
        if selected:
            resolve(record, run["config"])
        if record.get("findings"):
            flag(connection, run, record, title="Review written bill", kind="review", actor=user["id"])
        # One click authorizes the observed correction; no operation or values
        # are editable by the renderer. Native compare-and-readback still applies.
        if record.get("current"):
            record["operation"] = "update"
            connection.execute("UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(run["result"]), run["id"]))
        result = copy.deepcopy(run["result"])
        for position, row in enumerate(result["records"]):
            row["decision"] = "approve" if position == index else "hold"
        return approve_run(connection, tenant, user, run_id, {"result": result, "acknowledge_findings": True})
    except (ValueError, KeyError, TypeError) as error:
        raise ServiceError("invalid", "No supported write. Use Do nothing.") from error


def _retry_save(connection, tenant, user, run, index):
    """Re-send a held bill's supported proposal after the destination is fixed.

    This is a technical retry under the original authorization, not a new
    interpretation, so it opens no best-guess review. Native saves read the
    destination first: an equal voucher is skipped and a different one is
    offered as a correction rather than overwritten.
    """
    from .service import approve_run
    row = None if index is None else run["result"]["records"][index]
    if not row or row.get("status") != "held" or not row.get("save_hold"):
        raise ServiceError("invalid", "Only a held save can be retried.")
    reason = row.pop("save_hold")
    row["findings"] = [finding for finding in row["findings"] if finding != reason]
    connection.execute("UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(run["result"]), run["id"]))
    result = copy.deepcopy(run["result"])
    for position, other in enumerate(result["records"]):
        other["decision"] = "approve" if position == index else "hold"
    return approve_run(connection, tenant, user, run["id"], {"result": result, "acknowledge_findings": True})


def check_observation(item, observation):
    target = item["target"]
    if not isinstance(observation, dict) or observation.get("company_guid") != target.get("company_guid"):
        raise ServiceError("invalid", "Destination identity changed.")
    # Native observations are data. The server independently validates the
    # business identity and balanced accounting entries before completion.
    from .vouchers import observed_document
    current = observation.get("current")
    current = observed_document(current, target) if isinstance(current, dict) else None
    valid = False
    if current:
        try:
            entries = current["entries"]
            amounts = [Decimal(str(e["amount"])) for e in entries]
            valid = (current["invoice_number"] == target["invoice_number"]
                and current["vendor"] == target["vendor"] and bool(current.get("guid"))
                and bool(current.get("fingerprint")) and len(amounts) >= 2
                and all(v.is_finite() for v in amounts) and sum(amounts) == 0
                # The supplier is credited on purchases and debited on debit notes.
                and any(e["ledger"] == target["vendor"] and Decimal(str(e["amount"])) != 0 for e in entries))
        except (KeyError, TypeError, InvalidOperation):
            valid = False
    masters = observation.get("ledgers", [])
    if not isinstance(masters, list) or any(not isinstance(m, dict) for m in masters):
        raise ServiceError("invalid", "Invalid native masters.")
    names = [m.get("@_NAME", m.get("NAME")) for m in masters]
    supplier_valid = target.get("vendor") in names
    if item["kind"] == "supplier" and target.get("gst_supplier"):
        from .supplier_gst import scalar, verified_supplier
        supplier = observation.get("supplier")
        reference = next((m for m in masters if m.get("@_NAME", m.get("NAME")) == target["vendor"]), None)
        supplier_valid = (supplier_valid and verified_supplier(supplier, target["gst_supplier"])
            and scalar(supplier.get("@_NAME") or supplier.get("NAME")) == target["vendor"]
            and all(scalar(supplier.get(key)) == scalar(reference.get(key)) for key in ("GUID", "ALTERID")))
        if supplier_valid:
            supplier = {**supplier, **{key: scalar(supplier.get(key)) for key in ("GUID", "PARENT", "ALTERID")}}
            masters = [supplier if m is reference else m for m in masters]
    return {"valid": valid if item["kind"] != "supplier" else supplier_valid,
            "ledgers": names, "masters": masters, "current": current}


def written(connection, run, record, result):
    """A verified save resolves the blocked-write event, never the review event.

    The event belongs to the input file, which can hold several bills; it stays
    open while any other proposal from that file still awaits a decision.
    """
    from .tally_writes import SETTLED
    if any(r["source_file_id"] == record["source_file_id"] and r.get("status") not in SETTLED
           for r in result["records"]):
        return
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
    from minkops_platform.run_controls import control_state
    intent = control_state(connection, item["tenant_id"], run["task_id"])
    if intent != "active":
        if intent == "paused":
            # A write already underway may finish while paused. Preserve its
            # verified callback, but defer the newly authorized bill dispatch.
            masters = [m for m in observation["masters"] if m.get("@_NAME", m.get("NAME")) == target["vendor"]]
            connection.execute("UPDATE attention_items SET target=target || %s WHERE tenant_id=%s AND id=%s",
                (Jsonb({"supplier_continuation": {"valid": True, "masters": masters}}), item["tenant_id"], item["id"]))
        return
    if run["state"] not in ("review", "writing"):
        return
    from .client_context import select_target
    from .tally_writes import complete_run, prepare
    result = copy.deepcopy(run["result"])
    from .bulk_decisions import proposal_identity
    from .tally_writes import SETTLED
    consent = target.get("authorized_proposals")
    eligible = []
    for index, record in enumerate(result["records"]):
        if record.get("status") in SETTLED:
            continue
        authorized = (any(c["record_index"] == index and c["source_file_id"] == record["source_file_id"]
                          and c["identity"] == proposal_identity(record) for c in consent) if consent else
                      record["source_file_id"] == target["file_id"] and record["data"].get("vendor") == target["vendor"])
        if authorized:
            selected = select_target(record, run["config"]["tally_target"])
            if selected["references"]["company_guid"] != target["company_guid"]:
                continue
            eligible.append(record)
            if not consent:
                break
    if (item["status"] == "done" and not target.get("supplier_continuation")) or not eligible:
        return
    master = next(m for m in observation["masters"] if m.get("@_NAME", m.get("NAME")) == target["vendor"])
    if master.get("PARENT") != "Sundry Creditors" or not master.get("GUID"):
        raise ServiceError("invalid", "Supplier definition needs review.")
    for record in eligible:
        record["data"]["vendor"] = target["vendor"]
        # The verified native master joins this run's pinned company view.
        created = {"company_guid": target["company_guid"], "type": "LEDGER",
                   "data": {"NAME": target["vendor"], **{k: master.get(k) for k in ("GUID", "PARENT", "ALTERID")}}}
        if created not in run["config"].setdefault("created_masters", []):
            run["config"]["created_masters"].append(created)
        record["voucher"]["party"] = {"ledger_guid": master["GUID"], "new_supplier": False,
                                      "evidence": "Explicit supplier creation verified by native readback."}
        record["decision"] = "approve"
        sibling = connection.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s FOR UPDATE",
            (run["tenant_id"], f"bill:{run['id']}:{record['source_file_id']}:supplier")).fetchone()
        if sibling and sibling["id"] != item["id"]:
            connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s", (job["actor_id"], sibling["id"]))
            attention.audit(connection, sibling, job["actor_id"], "continued", "Authorized supplier verified; bill save queued.")
    for row in result["records"]:
        if not any(row is authorized for authorized in eligible) and row.get("status") not in ("saved", "duplicate", "writing", "rejected"):
            row["decision"] = "hold"
    connection.execute("UPDATE account_runs SET config=%s WHERE id=%s", (config_json(connection, run["tenant_id"], run["config"]), run["id"]))
    # The native-created master is scoped to this continuation. Other runs keep
    # their confirmed snapshots and must refresh discovery to see the new master.
    prepare(connection, run, result, approved=True)
    complete_run(connection, run, result)
    connection.execute("UPDATE attention_items SET target=target-'supplier_continuation' WHERE tenant_id=%s AND id=%s",
        (item["tenant_id"], item["id"]))
    attention.audit(connection, item, job["actor_id"], "continued", "Supplier verified. Bill save queued.")


def resume_suppliers(connection, run, user):
    # A live callback locks item -> run. Skip an item already held by that
    # callback: after Resume commits it sees active intent and continues itself.
    items = connection.execute("""SELECT * FROM attention_items WHERE tenant_id=%s AND task_id=%s
        AND target->>'run_id'=%s AND target ? 'supplier_continuation' FOR UPDATE SKIP LOCKED""",
        (run["tenant_id"], run["task_id"], str(run["id"]))).fetchall()
    for item in items:
        supplier_created(connection, item, {"actor_id": user["id"]}, item["target"]["supplier_continuation"])
