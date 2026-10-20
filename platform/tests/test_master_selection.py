"""Native identity selection is independent of invoice spelling and language."""
import copy

import pytest

from minkops_platform.accounts.bills import business_identity, target_from_references
from minkops_platform.accounts.master_selection import resolve_masters


def target(company="company-a", catalog="catalog-a", extra=()):
    return target_from_references({"company": company, "port": 9000, "collections": [
        {"category": "company", "status": "ready", "records": [{"GUID": company}]},
        {"category": "ledgers", "status": "ready", "records": [
            {"NAME": "A M Office Solutions", "GUID": "supplier", "PARENT": "Sundry Creditors"},
            {"NAME": "Office Purchases", "GUID": "purchase", "PARENT": "Purchase Accounts"},
            *extra,
        ]},
        {"category": "voucher_types", "status": "ready", "records": [{"NAME": "Purchase"}]},
    ]}, "device", catalog)


def record(t):
    refs = {r["name"]: key for key, r in t["ledger_refs"].items()}
    return {"data": {"vendor": "AM office solutons", "purchase_ledger": None,
                     "tax": 0, "tax_ledger": None, "invoice_number": "INV-1", "date": "2026-10-01"},
            "master_refs": {
                "vendor": {"ref": refs["A M Office Solutions"], "evidence": "Supplier GSTIN and address match."},
                "purchase_ledger": {"ref": refs["Office Purchases"], "evidence": "Office supplies; relevant prior voucher."},
                "tax_ledger": None}}


@pytest.mark.parametrize("spelling", ["AM Office Solutons", "A  M OFFICE SOLUTIONS", "ए एम ऑफिस सॉल्यूशन्स", None])
def test_reference_supplies_canonical_name_before_identity(spelling):
    t = target()
    r = record(t)
    r["data"]["vendor"] = spelling
    resolve_masters(r, t, required=True)
    assert r["data"]["vendor"] == "A M Office Solutions"
    assert r["data"]["purchase_ledger"] == "Office Purchases"
    assert business_identity(r["data"]) == business_identity({**r["data"], "vendor": "A M Office Solutions"})
    before = copy.deepcopy(r)
    resolve_masters(r, t, required=True)
    assert r == before


@pytest.mark.parametrize("other", [target("company-b"), target(catalog="catalog-b")])
def test_reference_cannot_cross_company_or_catalog(other):
    with pytest.raises(ValueError, match="reference"):
        resolve_masters(record(target()), other, required=True)


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("master_refs"),
    lambda r: r["master_refs"]["vendor"].update(ref="invented"),
    lambda r: r["master_refs"]["vendor"].update(evidence=" "),
    lambda r: r["master_refs"].update(vendor=None),
    lambda r: r["master_refs"].update(tax_ledger=r["master_refs"]["vendor"]),
])
def test_invalid_selection_never_falls_back_to_a_name(mutation):
    t = target()
    r = record(t)
    r["data"]["vendor"] = "A M Office Solutions"
    mutation(r)
    with pytest.raises(ValueError):
        resolve_masters(r, t, required=True)


def test_duplicate_native_names_cannot_be_flattened_by_writer():
    t = target(extra=[{"NAME": "A M Office Solutions", "GUID": "another"}])
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_masters(record(t), t, required=True)


def test_old_pinned_names_remain_compatible_and_optional_refs_are_checked():
    r = {"data": {"vendor": "Old Ledger"}}
    resolve_masters(r, {}, required=False)
    assert r["data"]["vendor"] == "Old Ledger"
    r["master_refs"] = {}
    with pytest.raises(ValueError):
        resolve_masters(r, {}, required=False)


def test_unresolved_match_is_not_a_new_supplier_and_resolution_is_atomic():
    t = target()
    r = record(t)
    r["master_refs"]["vendor"].update(ref=None)
    before = copy.deepcopy(r)
    with pytest.raises(ValueError, match="unresolved"):
        resolve_masters(r, t, required=True)
    assert r == before
    r["master_refs"]["vendor"]["new_supplier"] = True
    resolve_masters(r, t, required=True)
    assert r["data"]["vendor"] == "AM office solutons"
    assert r["data"]["purchase_ledger"] == "Office Purchases"
    r["master_refs"]["vendor"]["ref"] = next(iter(t["ledger_refs"]))
    with pytest.raises(ValueError, match="contradictory"):
        resolve_masters(r, t, required=True)


def test_only_exceptions_queues_clean_siblings_but_preserves_review_gates():
    from unittest.mock import patch

    from minkops_platform.accounts.tally_writes import prepare_automatic

    run = {"tenant_id": "tenant", "task_id": "task", "config": {
        "tally_target": {"master_selection_version": 1}, "review_mode": "only_exceptions"}}
    result = {"records": [{"source_file_id": "good", "findings": []},
                          {"source_file_id": "bad", "findings": ["unclear"]}],
              "findings": [], "unresolved": [{"source_file_id": "bad", "reason": "unclear"}]}
    with patch("minkops_platform.run_controls.control_state", return_value="active"), \
         patch("minkops_platform.accounts.tally_writes.prepare") as prepare, \
         patch("minkops_platform.accounts.tally_writes.complete_run"), \
         patch("minkops_platform.accounts.attention.flag") as flag:
        assert prepare_automatic(None, run, result)
        assert result["records"][1]["decision"] == "hold"
        assert "decision" not in result["records"][0]
        prepare.assert_called_once()
        assert [call.args[2]["source_file_id"] for call in flag.call_args_list] == ["bad"]
        for change in ({"requires_review": True}, {"findings": ["batch uncertainty"]}):
            assert not prepare_automatic(None, run, {**result, **change})
        run["config"]["review_mode"] = "all_outputs"
        assert not prepare_automatic(None, run, result)


def test_bill_dated_before_the_company_books_is_held_with_a_specific_reason():
    from minkops_platform.accounts.bills import HoldReason, validate_tally

    t = target()
    data = {"vendor": "A M Office Solutions", "purchase_ledger": "Office Purchases", "tax": 0,
            "tax_ledger": None, "invoice_number": "INV-1", "date": "2026-03-15",
            "subtotal": 100, "total": 100, "cost_code": None}
    validate_tally(data, t)  # Older pinned targets carry no books date and skip the check.
    with pytest.raises(HoldReason) as held:
        validate_tally(data, {**t, "books_from": "2026-04-01"})
    assert held.value.code == "date_before_books" and "2026-03-15" in str(held.value)
    validate_tally({**data, "date": "2026-04-01"}, {**t, "books_from": "2026-04-01"})


@pytest.mark.parametrize("field,selection,code", [
    ("purchase_ledger", {"ref": "foreign", "evidence": "Similar purpose."}, "classification_uncertain"),
    ("vendor", {"ref": "foreign", "evidence": "Similar name."}, "supplier_unresolved"),
    ("vendor", {"ref": None, "evidence": "Two suppliers fit."}, "supplier_unresolved"),
])
def test_server_holds_carry_codes_so_labels_do_not_guess_from_wording(field, selection, code):
    from minkops_platform.accounts.attention import exception_label
    from minkops_platform.accounts.bills import HoldReason, note_hold

    t = target()
    r = record(t)
    r["master_refs"][field] = selection
    with pytest.raises(HoldReason) as held:
        resolve_masters(r, t, required=True)
    assert held.value.code == code
    # Previously "outside this company's pinned discovery" was labelled "Unknown company".
    held_record = {"source_file_id": "bill", "findings": []}
    note_hold(held_record, held.value)
    assert exception_label(held_record) != "Unknown company"


def test_changed_native_identity_and_bill_arithmetic_have_specific_codes():
    from minkops_platform.accounts.bills import HoldReason, validate_tally

    t = target()
    r = record(t)
    changed = copy.deepcopy(t)
    changed["references"]["ledgers"]["Office Purchases"] = {"GUID": "purchase", "ALTERID": "99"}
    with pytest.raises(HoldReason) as held:
        resolve_masters(r, changed, required=True)
    assert held.value.code == "destination_changed"
    data = {"vendor": "A M Office Solutions", "purchase_ledger": "Office Purchases", "tax": 0,
            "tax_ledger": None, "invoice_number": "INV-1", "date": "2026-10-01",
            "subtotal": 100, "total": 101, "cost_code": None}
    with pytest.raises(HoldReason) as held:
        validate_tally(data, t)
    assert held.value.code == "source_values_conflict"
    with pytest.raises(HoldReason) as held:
        validate_tally({**data, "total": 100, "vendor": "Unknown Traders"}, t)
    assert held.value.code == "supplier_missing"
