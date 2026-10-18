"""Server-owned v1 eligibility for decisions over immutable bill proposals."""
import copy

from .bill_review import REASONS
from .bills import validate_tally
from .client_context import select_target


# The matrix is a ceiling. Complete values, positive supplier evidence and the
# pinned company/master identities can further restrict these actions.
HANDLERS = {code: ("nothing", "retry") for code in REASONS}
for _code in ("source_unreadable", "classification_uncertain", "manual_review"):
    HANDLERS[_code] = ("guess", "nothing", "retry")
HANDLERS["supplier_missing"] = ("supplier", "nothing", "retry")
for _code in ("company_not_open", "no_company", "duplicate_company", "not_running", "port_closed",
              "busy", "too_many", "invalid_response", "rejected", "save_held", "save_waiting",
              "save_interrupted", "pc_unavailable", "save_hold"):
    HANDLERS[_code] = ("retry_save", "nothing")


def supported_write(run, record, *, supplier=False):
    """Check eligibility without changing a proposal or trusting renderer flags."""
    scope = run["config"].get("tally_target")
    if not scope:
        return not supplier  # Pinned Excel runs retain their existing validation.
    candidate = copy.deepcopy(record)
    try:
        selected = select_target(candidate, scope)
        if scope.get("master_selection_version") == 1:
            from .master_selection import resolve_masters
            resolve_masters(candidate, selected, required=True, allow_split=scope.get("tax_allocation_version") == 1)
        if supplier:
            vendor = candidate["data"]["vendor"]
            refs = candidate.get("master_refs")
            if (vendor in selected["ledgers"]
                    or (refs is not None and refs.get("vendor", {}).get("new_supplier") is not True)
                    or not any(e.get("field") == "vendor" and e.get("quote", "").strip() for e in candidate.get("evidence", []))):
                return False
            from .supplier_gst import creation_plan
            creation_plan(run, candidate, selected)
            selected = {**selected, "ledgers": [*selected["ledgers"], vendor]}
        validate_tally(candidate["data"], selected, candidate.get("tax_allocations"))
        return True
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def allowed_actions(run, record):
    if run["state"] != "review" or record.get("status") in ("saved", "duplicate", "rejected", "writing"):
        return []
    unresolved = any(i["source_file_id"] == record["source_file_id"] for i in (run.get("result") or {}).get("unresolved", []))
    if record.get("save_hold"):
        return ["retry_save", "nothing"]
    codes = record.get("exception_codes") or [record.get("code") or "manual_review"]
    actions = list(HANDLERS.get(codes[0], ("nothing", "retry")))
    for code in codes[1:]:
        actions = [a for a in actions if a in HANDLERS.get(code, ("nothing", "retry"))]
    return [action for action in actions
            if (action != "retry" or unresolved)
            and (action != "guess" or supported_write(run, record))
            and (action != "supplier" or supported_write(run, record, supplier=True))]


def public_result(run):
    result = copy.deepcopy(run.get("result"))
    if not isinstance(result, dict):
        return result
    from .bulk_decisions import options
    bulk = options(run)
    for index, record in enumerate(result.get("records", [])):
        if isinstance(record, dict) and record.get("source_file_id"):
            record["allowed_actions"] = allowed_actions(run, record)
            record["bulk_actions"] = bulk.get((index, record["source_file_id"]), {})
    for issue in result.get("unresolved", []):
        issue["allowed_actions"] = allowed_actions(run, issue)
        issue["bulk_actions"] = bulk.get((None, issue["source_file_id"]), {})
    return result
