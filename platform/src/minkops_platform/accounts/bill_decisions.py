"""Server-owned v1 eligibility for decisions over immutable bill proposals."""
import copy

from .bill_review import REASONS
from .client_context import select_target

# The matrix is a ceiling. Complete values, positive supplier evidence and the
# pinned company/master identities can further restrict these actions.
HANDLERS = dict.fromkeys(REASONS, ("nothing", "retry"))
for _code in ("source_unreadable", "classification_uncertain", "manual_review", "posting_profile_miss"):
    HANDLERS[_code] = ("guess", "nothing", "retry")
HANDLERS["supplier_missing"] = ("supplier", "nothing", "retry")
for _code in ("company_not_open", "no_company", "duplicate_company", "not_running", "port_closed",
              "busy", "too_many", "invalid_response", "rejected", "save_held", "save_waiting",
              "save_interrupted", "pc_unavailable", "save_hold"):
    HANDLERS[_code] = ("retry_save", "nothing")


def write_blocker(run, record, *, supplier=False):
    """Explain ineligibility through the same gate used to accept the decision."""
    scope = run["config"].get("tally_target")
    if not scope:
        return ({"code": "decision_unavailable", "message": "Create this ledger requires a Tally destination."}
                if supplier else None)  # Pinned Excel runs retain existing validation.
    candidate = copy.deepcopy(record)
    try:
        from .vouchers import resolve

        if supplier:
            selected = select_target(candidate, scope)
            party = candidate["voucher"]["party"]
            if (party.get("ledger_guid") is not None or party.get("new_supplier") is not True
                    or not any(e.get("field") == "supplier" and e.get("quote", "").strip()
                               for e in candidate.get("evidence", []))):
                raise ValueError("Creating this ledger requires a positively identified new supplier and printed evidence.")
            from .supplier_gst import creation_plan
            from .vouchers import summary
            candidate["data"] = summary(candidate, run["config"])
            creation_plan(run, candidate, selected)
        resolve(candidate, run["config"], assume_new_supplier=supplier)
        return None
    except ValueError as error:
        return {"code": getattr(error, "code", "decision_unavailable"), "message": str(error)}
    except (KeyError, TypeError, AttributeError):
        return {"code": "decision_unavailable", "message": "The pinned proposal is incomplete. Recheck the bill with complete Source Discovery."}


def supported_write(run, record, *, supplier=False):
    """Check eligibility without changing a proposal or trusting renderer flags."""
    return write_blocker(run, record, supplier=supplier) is None


def action_options(run, record):
    if run["state"] != "review" or record.get("status") in ("saved", "duplicate", "rejected", "writing"):
        return [], {}
    unresolved = any(i["source_file_id"] == record["source_file_id"] for i in (run.get("result") or {}).get("unresolved", []))
    if record.get("save_hold"):
        return ["retry_save", "nothing"], {}
    if run["config"].get("_public_projection"):
        return [action for action in record.get("allowed_actions", []) if action != "retry" or unresolved], record.get("unavailable_actions", {})
    codes = record.get("exception_codes") or [record.get("code") or "manual_review"]
    actions = list(HANDLERS.get(codes[0], ("nothing", "retry")))
    for code in codes[1:]:
        actions = [a for a in actions if a in HANDLERS.get(code, ("nothing", "retry"))]
    unavailable = {action: reason for action in actions if action in ("guess", "supplier")
                   and (reason := write_blocker(run, record, supplier=action == "supplier"))}
    return [action for action in actions if action not in unavailable and (action != "retry" or unresolved)], unavailable


def allowed_actions(run, record):
    return action_options(run, record)[0]


def public_result(run):
    result = copy.deepcopy(run.get("result"))
    if not isinstance(result, dict):
        return result
    if result.get("_decision_projection"):
        run = {**run, "config": {**run["config"], "_public_projection": True}}
    from .bulk_decisions import options
    bulk = options(run)
    for index, record in enumerate(result.get("records", [])):
        if isinstance(record, dict) and record.get("source_file_id"):
            record["allowed_actions"], record["unavailable_actions"] = action_options(run, record)
            record["bulk_actions"] = bulk.get((index, record["source_file_id"]), {})
    for issue in result.get("unresolved", []):
        issue["allowed_actions"], issue["unavailable_actions"] = action_options(run, issue)
        issue["bulk_actions"] = bulk.get((None, issue["source_file_id"]), {})
    return result


def pin_decisions(run, result):
    """Compute display controls once against the validated immutable proposal.

    This is never an authorization receipt: consequential paths re-run the
    actual eligibility gates against their locked authoritative run.
    """
    clean = {key: value for key, value in result.items() if key != "_decision_projection"}
    result = public_result({**run, "state": "review", "result": clean})
    result["_decision_projection"] = 1
    return result
