"""Approved Tally intents, native receipts and per-bill handoffs."""

import json
from uuid import NAMESPACE_URL, uuid5

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError

from .bills import add_note, allocation_entries
from .repository import observe, run_for

PC_UNAVAILABLE = "Destination PC is unavailable. Reconnect it, then use Retry save."
# Short labels for typed holds the companion reports before or instead of a
# write (connectors/desktop/src/tally.js saveTallyBill). Unknown codes fall back.
HOLD_TITLES = {
    "company_not_open": "Open company in Tally",
    "no_company": "Open company in Tally",
    "duplicate_company": "Duplicate company open",
    "not_running": "Tally unavailable",
    "port_closed": "Tally unavailable",
    "busy": "Tally unavailable",
    "too_many": "Tally unavailable",
    "invalid_response": "Tally unavailable",
    "rejected": "Tally rejected bill",
}


def hold_save(connection, run, record, reason, *, title=None):
    """Hold a supported proposal for a destination-side reason.

    `save_hold` marks blockers that a retry of the same approved plan can clear
    once the destination is fixed; interpretation uncertainty never sets it.
    """
    from .attention import flag

    record["status"] = "held"
    record["save_hold"] = reason
    from .bill_review import TITLE_CODES
    record["save_hold_code"] = TITLE_CODES.get(title, "save_held")
    record["findings"] = list(dict.fromkeys([*record["findings"], reason]))
    return flag(connection, run, record, title=title, reopen=True)


def prepare_automatic(connection, run, result):
    """The selected exception-only mode authorizes clean bills independently.

    Client-wide review gates still apply to the full batch. Native duplicate,
    identity/version and exact readback checks are identical to explicit writes.
    """
    from minkops_platform.run_controls import control_state
    from minkops_platform.workflow_policies import enforce_policies

    if (run["config"].get("review_mode") != "only_exceptions"
            or run["config"].get("tally_target", {}).get("master_selection_version") != 1
            or enforce_policies(run["config"], result).get("requires_review")
            or result.get("findings")
            or control_state(connection, run["tenant_id"], run["task_id"]) != "active"):
        return False
    from .attention import flag

    unresolved = {issue["source_file_id"] for issue in result.get("unresolved", [])}
    rechecked = run["config"].get("retry_file_id")
    for record in result["records"]:
        flagged = record.get("findings") or record["source_file_id"] in unresolved
        if flagged and record.get("status") not in ("saved", "duplicate", "writing", "rejected"):
            record["decision"] = "hold"
            # Under standing authorization the exceptions are the work; they
            # belong in shared attention, not only in this run's review.
            # Only a rechecked input's hold is new; siblings are restated.
            flag(connection, run, record, reopen=record["source_file_id"] == rechecked)
    prepare(connection, run, result)
    complete_run(connection, run, result)
    return True


def prepare(connection, run, result, *, approved=False):
    from minkops_platform.workflow_policies import enforce_policies

    if enforce_policies(run["config"], result).get("requires_review") and not approved:
        raise ValueError("Client policy requires explicit review before destination writes.")
    from .vouchers import resolve

    seen = {}
    ordered = sorted(
        enumerate(result["records"]), key=lambda pair: pair[1].get("company_guid") or ""
    )
    candidates, errors, groups = {}, {}, {}
    # Compare the complete accounting versions before enqueuing any intent.
    # Otherwise the first conflicting duplicate could be written by ordering.
    for index, record in ordered:
        if record.get("status") in ("saved", "duplicate", "rejected", "writing") or record.get("decision") in ("hold", "reject"):
            continue
        try:
            bill = resolve(record, run["config"])
            candidates[index] = bill
            groups.setdefault((bill.target["destination_key"], bill.identity), []).append(index)
        except ValueError as error:
            errors[index] = str(error)
    for indexes in groups.values():
        if len({candidates[i].accounting() for i in indexes}) > 1:
            for index in indexes:
                errors[index] = "This batch contains conflicting versions of the same bill. Review the correction separately."
    for index, record in ordered:
        if (
            record.get("status") in ("saved", "duplicate", "rejected", "writing")
            or record.get("decision") == "hold"
        ):
            continue
        if record.get("decision") == "reject":
            record["status"] = "rejected"
            continue
        try:
            if index in errors:
                raise ValueError(errors[index])
            bill = candidates[index]
            target, identity = bill.target, bill.identity
            key = (target["destination_key"], identity)
            if key in seen:
                if candidates[seen[key]].accounting() == bill.accounting():
                    record["duplicate_of"] = seen[key]
                    record["status"] = "writing"
                    continue
                raise ValueError(
                    "This batch contains conflicting versions of the same bill. Review the correction separately."
                )
            if record["operation"] == "update" and not record.get("current"):
                raise ValueError(
                    "First reconcile the existing voucher before approving a correction."
                )
            token = str(
                uuid5(
                    NAMESPACE_URL,
                    f"minkops:{run['tenant_id']}:{target['destination_key']}:{identity}",
                )
            )
            plan = bill.native_plan(token, record["operation"], record.get("current"))
            try:
                with connection.transaction():
                    write = connection.execute(
                        """INSERT INTO account_tally_writes
                        (tenant_id,run_id,device_id,company,identity,record_index,plan,destination_key)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (
                            run["tenant_id"],
                            run["id"],
                            target["device_id"],
                            target["company"],
                            identity,
                            index,
                            Jsonb(plan),
                            target["destination_key"],
                        ),
                    ).fetchone()
                    from minkops_platform.desktop import enqueue_approved

                    enqueue_approved(connection, run, target["device_id"], "tally.save", write["id"])
            except ServiceError:
                # An operator's click reports the offline PC immediately. Background
                # dispatch has no one to answer, so the savepoint discards the
                # intent and the bill waits for an explicit Retry save instead.
                if approved:
                    raise
                hold_save(connection, run, record, PC_UNAVAILABLE, title="PC unavailable")
                continue
            record["status"] = "writing"
            seen[key] = index
        except ValueError as error:
            from .attention import flag
            from .bills import note_hold
            record["status"] = "held"
            note_hold(record, error)
            flag(connection, run, record, reopen=True)
        except UniqueViolation:
            hold_save(connection, run, record,
                      "Another approved run is reconciling this bill. Finish it, then use Retry save.",
                      title="Save waiting")
    return result


SETTLED = ("writing", "saved", "duplicate", "rejected")


def settle_unresolved(result):
    """An input stops being unresolved once every proposal for it is settled.

    Approval rebuilds results from the stored proposal, so state must follow
    record outcomes rather than whichever action cleared an issue. Inputs with
    a held or pending proposal stay unresolved, keeping Recheck bill available.
    """
    statuses = {}
    for record in result["records"]:
        statuses.setdefault(record["source_file_id"], []).append(record.get("status"))
    result["unresolved"] = [
        issue for issue in result.get("unresolved", [])
        if not all(status in SETTLED for status in statuses.get(issue["source_file_id"], [None]))
    ]
    return result


def defer_input(result, file_id):
    """Record Do nothing as data, final for this run.

    A run-level finding would block exception-only automation for every later
    sibling. The actor and the pending manual handoff live in attention.
    """
    deferred = result.setdefault("deferred", [])
    if not any(item["source_file_id"] == file_id for item in deferred):
        issue = next((i for i in result.get("unresolved", []) if i["source_file_id"] == file_id), {})
        deferred.append({"source_file_id": file_id, **{k: issue[k] for k in ("code", "reason") if k in issue}})
    result["unresolved"] = [i for i in result.get("unresolved", []) if i["source_file_id"] != file_id]
    return result


def complete_run(connection, run, result):
    from .attention import flag
    settle_unresolved(result)
    for record in result["records"]:
        if record.get("status") == "held":
            flag(connection, run, record)
    pending_excel = connection.execute(
        "SELECT count(*) AS n FROM account_writes WHERE tenant_id=%s AND run_id=%s AND verified_at IS NULL AND cancelled_at IS NULL",
        (run["tenant_id"], run["id"]),
    ).fetchone()["n"]
    pending_tally = connection.execute(
        "SELECT count(*) AS n FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s AND finished_at IS NULL AND cancelled_at IS NULL",
        (run["tenant_id"], run["id"]),
    ).fetchone()["n"]
    held = bool(result.get("unresolved")) or any(
        r.get("status") in (None, "held") for r in result["records"]
    )
    state = "writing" if pending_excel or pending_tally else "review" if held else "completed"
    connection.execute(
        "UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s",
        (Jsonb(result), run["tenant_id"], run["id"]),
    )
    device = pending_tally and connection.execute(
        "SELECT name FROM desktop_devices WHERE tenant_id=%s AND id=%s",
        (run["tenant_id"], run["config"].get("tally_target", {}).get("device_id")),
    ).fetchone()
    summary = {
        # Saves wait for the destination PC; an offline PC is the usual cause.
        "writing": f"Saving to Tally on {device['name']}. Keep Minkops running on that PC." if device
        else "Approved entries are waiting for verified destination writes.",
        "review": "Successful entries are preserved. Review only the bills needing attention.",
        "completed": "Bill entries verified. Exact duplicates were skipped without adding records.",
    }[state]
    observe(
        connection,
        run,
        state,
        summary,
        100 if state == "completed" else 85 if state == "writing" else 70,
    )


def spec(connection, device, payload, *, pending=True, underway=False):
    run = run_for(connection, device["tenant_id"], payload["run_id"], True)
    if pending and not underway:
        from minkops_platform.run_controls import require_active
        require_active(connection, device["tenant_id"], run["task_id"])
    if run["actor_id"] != device["owner_id"]:
        raise ServiceError("not_found", "Approved run not found for this account.")
    row = connection.execute(
        "SELECT * FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s AND id=%s AND device_id=%s FOR UPDATE",
        (device["tenant_id"], run["id"], payload["write_id"], device["id"]),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Approved Tally write not found for this PC.")
    if pending and (run["state"] != "writing" or row["finished_at"] or row["cancelled_at"]):
        raise ServiceError("conflict", "This Tally write is no longer pending.")
    return run, row


def accept(connection, device, payload, receipt):
    run, write = spec(connection, device, payload, pending=False)
    if not isinstance(receipt, dict) or receipt.get("outcome") not in (
        "saved",
        "duplicate",
        "correction",
        "attention",
    ):
        raise ServiceError("invalid", "Invalid Tally write receipt.")
    outcome = receipt["outcome"]
    current = receipt.get("current")
    if outcome in ("saved", "duplicate", "correction") and isinstance(current, dict) and "lines" in current:
        # Protocol 5: verify against the plan this companion was served.
        from .vouchers import observed_bill, upgrade

        plan = upgrade(write["plan"], identity=write["identity"])
        if plan is None:
            raise ServiceError("invalid", "This approved bill was not served as a protocol 5 voucher.")
        try:
            current = observed_bill(plan, outcome, current, identity=write["identity"])
        except ValueError as error:
            raise ServiceError("invalid", str(error)) from error
    elif outcome in ("saved", "duplicate", "correction"):
        if not isinstance(current, dict) or set(current) - {"voucher_type"} != {
            "master_id",
            "guid",
            "date",
            "invoice_number",
            "vendor",
            "entries",
            "fingerprint",
        }:
            raise ServiceError("invalid", "Tally receipt must contain an observed voucher.")
        # Companions from 0.7.0 report the observed voucher type; older ones omit it.
        if "voucher_type" in current and (
            not isinstance(current["voucher_type"], str) or not 1 <= len(current["voucher_type"]) <= 200
        ):
            raise ServiceError("invalid", "Invalid observed voucher type.")
        if (
            any(
                not isinstance(current[k], str) or not 1 <= len(current[k]) <= 200
                for k in ("master_id", "guid", "date", "invoice_number", "vendor", "fingerprint")
            )
            or not isinstance(current["entries"], list)
            or not 1 <= len(current["entries"]) <= 100
        ):
            raise ServiceError("invalid", "Invalid observed voucher.")
        if any(
            not isinstance(e, dict)
            or set(e) != {"ledger", "amount"}
            or not isinstance(e["ledger"], str)
            or type(e["amount"]) is not int
            for e in current["entries"]
        ):
            raise ServiceError("invalid", "Invalid ledger readback.")
        from .bills import business_identity

        actual = {
            "vendor": current["vendor"],
            "invoice_number": current["invoice_number"],
            "date": f"{current['date'][:4]}-{current['date'][4:6]}-{current['date'][6:]}",
        }
        try:
            if business_identity(actual) != write["identity"]:
                raise ValueError()
        except ValueError as error:
            raise ServiceError("invalid", "Readback belongs to a different bill.") from error
        if outcome in ("saved", "duplicate"):
            from decimal import Decimal

            data = write["plan"]["data"]

            def money(v):
                return int(Decimal(str(v)) * 100)

            expected = [
                {"ledger": data["vendor"], "amount": money(data["total"])},
                {"ledger": data["purchase_ledger"], "amount": -money(data["subtotal"])},
            ]
            expected.extend({"ledger": line["ledger"], "amount": -money(line["amount"])}
                            for line in allocation_entries(data, write["plan"].get("tax_allocations")))

            def key(e):
                return e["ledger"], e["amount"]

            if current["date"] != data["date"].replace("-", "") or sorted(
                current["entries"], key=key
            ) != sorted(expected, key=key):
                raise ServiceError(
                    "conflict", "Tally readback differs from the approved amounts or ledgers."
                )
            if (
                outcome == "saved"
                and write["plan"].get("expected")
                and current["guid"] != write["plan"]["expected"]["guid"]
            ):
                raise ServiceError("conflict", "Tally returned a different voucher identifier.")
    result = json.loads(json.dumps(run["result"]))
    record = result["records"][write["record_index"]]
    record["status"] = outcome if outcome in ("saved", "duplicate") else "held"
    for sibling in result["records"]:
        if sibling.get("duplicate_of") == write["record_index"]:
            sibling["status"] = "duplicate" if outcome in ("saved", "duplicate") else "held"
            if outcome in ("saved", "duplicate"):
                add_note(sibling, "Repeated bill in this batch was skipped.")
            else:
                sibling["findings"].append(
                    "The original bill needs attention; this repeated input was not written.")
    if current:
        record["current"] = current
    from .attention import flag
    if outcome in ("correction", "attention"):
        # A different existing voucher is a correction decision. Any other native
        # refusal is fixed in Tally, then cleared by retrying the same plan.
        item = (flag(connection, run, record, title="Review in Tally", reopen=True) if outcome == "correction"
                else hold_save(connection, run, record,
                               str(receipt.get("message", "Tally write needs attention."))[:300],
                               title=HOLD_TITLES.get(receipt.get("hold"), "Review in Tally")))
        from ..attention import audit
        audit(connection,item,run['actor_id'],outcome,receipt.get('message','Existing voucher needs review.'))
    # Best-guess review starts after verified write, using exact native identity.
    if current and outcome in ("saved", "duplicate"):
        from .attention import written
        written(connection, run, record, result)
        connection.execute("UPDATE attention_items SET target=target||%s,updated_at=now() WHERE tenant_id=%s AND event_key=%s AND status='pending'",
            (Jsonb({"baseline": current, "date": record["data"].get("date")}), run["tenant_id"],
             f"bill:{run['id']}:{record['source_file_id']}:review"))
    if outcome == "duplicate":
        add_note(record, "Exact duplicate already exists; no additional voucher was created.")
    elif outcome == "correction":
        record["findings"].append("Review in Tally.")
    connection.execute(
        "UPDATE account_tally_writes SET outcome=%s,receipt=%s,finished_at=now(),verified_at=CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s",
        (outcome, Jsonb(receipt), outcome in ("saved", "duplicate"), write["id"]),
    )
    if run["state"] == "writing":
        complete_run(connection, run, result)
    else:
        connection.execute(
            "UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(result), run["id"])
        )
    return {"verified": outcome in ("saved", "duplicate"), "outcome": outcome}
