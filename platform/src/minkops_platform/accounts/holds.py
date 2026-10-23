"""The closed list of hold codes and the one-click actions each code allows.

A hold is a typed reason a bill or statement row cannot be saved as proposed,
raised by the model's coded exceptions, a server check or the native writer.
The server owns this matrix: renderers display it and decision paths enforce
it. The actions are a ceiling. Record-specific gates may remove one (Create
this ledger needs evidenced supplier details), never add one. A code outside
the list keeps only the actions that cannot write.
"""

from dataclasses import dataclass

# Every one-click decision a hold can offer, with its button label.
ACTIONS = {
    "nothing": "Do nothing",
    "retry": "Recheck",
    "guess": "Best guess write",
    "supplier": "Create this ledger",
    "retry_save": "Retry save",
    "settle": "Settle",
}
NON_WRITING = ("nothing", "retry")
BILL, STATEMENT = "bill", "statement"
# Where a code comes from: a coded exception (the model or a server check), a
# native writer hold, or the run's own review and save lifecycle.
EXCEPTION, NATIVE, LIFECYCLE = "exception", "native", "lifecycle"


@dataclass(frozen=True)
class Hold:
    code: str
    kind: str
    label: str
    reason: str
    actions: tuple[str, ...]
    scopes: frozenset[str]

    @property
    def destination(self):
        """Fixing Tally or the PC and retrying the same approved plan can clear it."""
        return "retry_save" in self.actions

    def reason_for(self, scope):
        """Sentences name a bill; for a statement row they name an entry."""
        if scope != STATEMENT:
            return self.reason
        return self.reason.replace("this bill", "this entry").replace("This bill", "This entry")


def _holds(scopes, actions, entries):
    return [Hold(code, kind, label, reason, actions, frozenset(scopes)) for code, kind, label, reason in entries]


_INTERPRETATION = ("guess", "nothing", "retry")
_DESTINATION = ("retry_save", "nothing")
_CATALOG = [
    *_holds((BILL, STATEMENT), NON_WRITING, [
        ("company_unresolved", EXCEPTION, "Company unclear", "The destination company could not be identified reliably."),
        ("unsupported_structure", EXCEPTION, "Manual entry needed",
         "This bill requires accounting entries outside the supported save format."),
    ]),
    # Neither recheck nor retry can clear these: Stop is final, and a run's books stay as it read them.
    *_holds((BILL, STATEMENT), ("nothing",), [
        ("run_stopped", LIFECYCLE, "Run stopped", "The run was stopped before this bill was saved."),
        ("destination_changed", NATIVE, "Tally changed",
         "A ledger, voucher type or cost allocation changed in Tally after this run read the books. Start a new run "
         "to enter this bill."),
    ]),
    *_holds((BILL,), NON_WRITING, [
        ("not_a_bill", EXCEPTION, "Not a bill", "This source does not contain a bill that can be entered."),
        ("multiple_bills_unclear", EXCEPTION, "Unclear bill count",
         "The separate bills in this file could not be identified reliably."),
        ("required_value_missing", EXCEPTION, "Missing bill value",
         "A required bill value could not be confirmed from the source."),
        ("source_values_conflict", EXCEPTION, "Bill values conflict", "The source contains conflicting bill values."),
        ("supplier_unresolved", EXCEPTION, "Supplier unclear",
         "The supplier could not be matched to exactly one Tally ledger."),
        ("date_before_books", EXCEPTION, "Before books begin",
         "The bill date is before the company's books beginning date."),
        ("identity_rule_unknown", EXCEPTION, "Foreign supplier",
         "A foreign supplier's invoice numbering cannot be checked for duplicates; enter it in Tally."),
        ("date_outside_company_period", EXCEPTION, "Outside company year",
         "The bill date is outside the routed company's year and no single sibling company covers it."),
        ("voucher_type_unresolved", EXCEPTION, "Voucher type needed",
         "A supported voucher type must be selected for this company."),
        ("extraction_failed", EXCEPTION, "Recheck bill", "The bill could not be processed and needs an explicit recheck."),
    ]),
    *_holds((BILL, STATEMENT), _INTERPRETATION, [
        ("classification_uncertain", EXCEPTION, "Ledger unclear",
         "The appropriate accounting ledger could not be confirmed."),
    ]),
    *_holds((BILL,), _INTERPRETATION, [
        ("source_unreadable", EXCEPTION, "Unreadable bill", "The bill could not be read reliably."),
    ]),
    *_holds((BILL,), ("supplier", "nothing", "retry"), [
        ("supplier_missing", EXCEPTION, "Missing supplier",
         "The supplier is missing from the company's confirmed Tally ledgers."),
    ]),
    # Released by the answer in Attention; a recheck could not answer it.
    *_holds((BILL,), ("nothing",), [
        ("practice_question", LIFECYCLE, "Practice question",
         "This bill waits for an answer in Attention about how its company keeps its books."),
    ]),
    *_holds((BILL, STATEMENT), _DESTINATION, [
        ("company_not_open", NATIVE, "Open company in Tally",
         "The destination company must be open in Tally before this bill can be saved."),
        ("no_company", NATIVE, "Open company in Tally",
         "The destination company must be open in Tally before this bill can be saved."),
        ("duplicate_company", NATIVE, "Duplicate company open",
         "More than one open Tally company matches the destination identity."),
        ("not_running", NATIVE, "Tally unavailable", "Tally must be running and connected before this bill can be saved."),
        ("port_closed", NATIVE, "Tally unavailable", "Tally's local connection is unavailable."),
        ("busy", NATIVE, "Tally unavailable", "Tally is busy and could not complete the save."),
        ("too_many", NATIVE, "Tally unavailable", "Tally returned too many matching destinations to save safely."),
        ("invalid_response", NATIVE, "Tally unavailable", "Tally's response could not be verified."),
        ("rejected", NATIVE, "Tally rejected bill", "Tally rejected this bill and its destination settings need attention."),
        ("save_waiting", LIFECYCLE, "Save waiting", "This bill is waiting for its destination before saving."),
        ("save_interrupted", LIFECYCLE, "Save interrupted",
         "The save was interrupted and its destination needs reconciliation."),
        ("save_held", LIFECYCLE, "Review in Tally", "This bill could not be saved and needs attention in the destination."),
    ]),
    # Statement rows. A source failure is corrected in the original file and
    # rerun; an uncertain or possibly existing entry is never written blindly.
    *_holds((STATEMENT,), ("nothing",), [
        ("statement_format", EXCEPTION, "Unreadable statement",
         "Use a readable CSV or XLSX statement; convert legacy XLS files in Excel."),
        ("statement_layout_unconfirmed", EXCEPTION, "Layout unconfirmed",
         "This statement layout is waiting for one confirmation in Attention."),
        ("statement_value", EXCEPTION, "Unreadable row", "A required date, amount or running balance is missing or invalid."),
        ("statement_balance", EXCEPTION, "Balance mismatch",
         "The running balance cannot be verified against the preceding balance and transaction."),
        ("statement_closing", EXCEPTION, "Closing mismatch",
         "The printed closing balance differs from the last running balance; a transaction may be missing."),
        ("statement_summary", EXCEPTION, "Summary mismatch",
         "The statement summary could not be verified against its transactions."),
        ("statement_formula", EXCEPTION, "Uncached formula",
         "A formula has no cached value. Recalculate and save the source in Excel."),
        ("statement_conflict", EXCEPTION, "Conflicting rows", "Overlapping files route the same bank transaction differently."),
        ("possible_existing", NATIVE, "Possible existing entry",
         "A voucher of the same amount on this bank may already record this row. Verify it in Tally before entering it by hand."),
        ("uncertain_import", NATIVE, "Import uncertain",
         "The import was interrupted. Reconcile Tally; Minkops will not resend an uncertain import."),
    ]),
    *_holds((STATEMENT,), NON_WRITING, [
        ("statement_layout_unknown", EXCEPTION, "Layout not proved",
         "No reading of this sheet was confirmed by the statement's own balances and totals."),
        ("statement_layout_changed", EXCEPTION, "Layout changed",
         "This statement's layout changed and could not be verified."),
        ("statement_transfer_unpaired", EXCEPTION, "Transfer unpaired",
         "The two legs of this transfer do not match each other."),
    ]),
    *_holds((STATEMENT,), _INTERPRETATION, [
        ("statement_interpretation", EXCEPTION, "Ledger unclear", "The ledger for this transaction could not be confirmed."),
        ("ledger_unresolved", EXCEPTION, "Other side unclear",
         "The other side of this transaction could not be matched to exactly one Tally ledger."),
        ("branch_unresolved", EXCEPTION, "Routing label unclear",
         "The client's routing label on this row could not be interpreted."),
    ]),
    # A person chooses which open bills a payment settles, from the allocations the books leave open.
    *_holds((STATEMENT,), ("settle", "nothing", "retry"), [
        ("bill_unresolved", EXCEPTION, "Settlement unclear",
         "Which of the party's open invoices this entry settles needs a person's choice."),
    ]),
    *_holds((STATEMENT,), _DESTINATION, [
        ("statement_save_waiting", LIFECYCLE, "Save waiting", "Another approved run is reconciling this transaction."),
        ("statement_save_held", LIFECYCLE, "Save held",
         "The native save could not be verified. Check Tally and the selected company."),
    ]),
]
HOLDS = {hold.code: hold for hold in _CATALOG}
assert len(HOLDS) == len(_CATALOG), "Hold codes must be unique."
# A code outside the list, or a hold with none, can never write.
UNKNOWN = Hold("manual_review", LIFECYCLE, "Needs review", "This bill needs manual review in the original system.",
               NON_WRITING, frozenset((BILL, STATEMENT)))


def hold(code):
    """The hold for a code; an unknown code keeps only non-writing actions."""
    return HOLDS.get(code, UNKNOWN)


def actions(codes):
    """The actions every one of a record's codes allows, in the first code's order."""
    codes = [code for code in codes if code] or [UNKNOWN.code]
    allowed = list(hold(codes[0]).actions)
    for code in codes[1:]:
        allowed = [action for action in allowed if action in hold(code).actions]
    return tuple(allowed)


def view(attribute, *, scope, kinds=(EXCEPTION, NATIVE, LIFECYCLE)):
    """{code: label|reason} for one scope, as the projections and Attention read them."""
    return {code: (h.reason_for(scope) if attribute == "reason" else getattr(h, attribute))
            for code, h in HOLDS.items() if scope in h.scopes and h.kind in kinds}
