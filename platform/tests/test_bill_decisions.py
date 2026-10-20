"""A single server policy controls both offered and accepted decisions."""
import copy

import pytest

from minkops_platform.accounts.bill_decisions import HANDLERS, allowed_actions
from minkops_platform.accounts.bill_review import REASONS
from minkops_platform.accounts.checks import EXCEPTION_LABELS
from minkops_platform.accounts.tally_writes import HOLD_TITLES
from minkops_platform.resources import REPOSITORY_ROOT


def example():
    record = {"source_file_id": "file", "findings": [], "evidence": [{"field": "vendor", "quote": "Supplier"}],
              "data": {"invoice_number": "T-1", "vendor": "Supplier", "date": "2026-10-02", "subtotal": 100,
                       "tax": 18, "tax_ledger": "Tax", "total": 118, "purchase_ledger": "Purchases", "cost_code": None}}
    run = {"state": "review", "config": {"tally_target": {"discovery_id": "d", "company": "Test Company",
           "ledgers": ["Supplier", "Purchases", "Tax"]}}, "result": {"records": [record], "unresolved": []}}
    return run, record


def test_matrix_is_exhaustive_and_documented():
    import re
    assert set(EXCEPTION_LABELS) | set(HOLD_TITLES) | {"save_hold"} <= set(HANDLERS)
    docs = (REPOSITORY_ROOT / "docs/bill-entry.md").read_text()
    labels = {"guess": "Best guess write", "nothing": "Do nothing", "retry": "Recheck",
              "retry_save": "Retry save", "supplier": "Create this ledger"}
    documented = {code: {action for action, label in labels.items() if label in line}
                  for line in docs.splitlines() if line.startswith("| `")
                  for code in re.findall(r"`([a-z_]+)`", line.split("|")[1])}
    assert documented == {code: set(actions) for code, actions in HANDLERS.items()}
    assert set(REASONS) <= set(HANDLERS)


@pytest.mark.parametrize("code", ["company_unresolved", "supplier_unresolved", "required_value_missing",
    "source_values_conflict", "unsupported_structure", "date_before_books", "destination_changed", "voucher_type_unresolved",
    "identity_rule_unknown"])
def test_identity_or_structure_blockers_never_offer_best_guess(code):
    run, record = example()
    record["exception_codes"] = [code]
    assert "guess" not in allowed_actions(run, record)


def test_supported_guess_and_save_retry_do_not_share_policy():
    run, record = example()
    record["exception_codes"] = ["classification_uncertain"]
    assert allowed_actions(run, record) == ["guess", "nothing"]
    record.update(status="held", save_hold="Diagnostic")
    assert allowed_actions(run, record) == ["retry_save", "nothing"]
    record["status"] = "saved"
    assert allowed_actions(run, record) == []


def test_mandatory_values_are_checked_before_offering_a_write_without_mutating_proposal():
    run, record = example()
    record["exception_codes"] = ["source_unreadable"]
    before = copy.deepcopy(run)
    assert "guess" in allowed_actions(run, record)
    assert run == before
    record["data"]["total"] = 1000
    assert "guess" not in allowed_actions(run, record)


def test_recheck_only_applies_to_unresolved_inputs_and_supplier_needs_positive_identity():
    run, record = example()
    record["exception_codes"] = ["supplier_missing"]
    record["data"].update(vendor="New supplier", tax=0, tax_ledger=None, total=100)
    assert allowed_actions(run, record) == ["supplier", "nothing"]
    run["result"]["unresolved"] = [{"source_file_id": "file", "code": "supplier_missing"}]
    assert allowed_actions(run, record) == ["supplier", "nothing", "retry"]
    record["master_refs"] = {"vendor": {"new_supplier": False}}
    assert "supplier" not in allowed_actions(run, record)
