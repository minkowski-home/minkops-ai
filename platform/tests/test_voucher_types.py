"""Purchase voucher types come from discovered masters, never a hard-coded name."""

import pytest

from minkops_platform.accounts.voucher_types import (
    apply_choices,
    base_types,
    candidates,
    pin,
    summary,
)

PURCHASE = {"@_NAME": "Purchase", "@_RESERVEDNAME": "Purchase", "PARENT": "Purchase", "GUID": "vt-p", "ALTERID": "1"}
GST = {"@_NAME": "Purchase GST", "@_RESERVEDNAME": "", "PARENT": {"#text": "Purchase", "@_TYPE": "String"},
       "GUID": "vt-g", "ALTERID": " 5", "ISACTIVE": "Yes"}
OLD = {"@_NAME": "Purchase Old", "PARENT": "Purchase", "GUID": "vt-o", "ISACTIVE": "No"}
BRANCH = {"@_NAME": "Purchase GST Mumbai", "PARENT": "purchase gst", "GUID": "vt-m"}
ORDER = {"@_NAME": "Purchase Order", "@_RESERVEDNAME": "Purchase Order", "PARENT": "Purchase Order", "GUID": "vt-po"}
JOURNAL = {"@_NAME": "Journal", "@_RESERVEDNAME": "Journal", "GUID": "vt-j"}
LOOP = [{"@_NAME": "Loop A", "PARENT": "Loop B", "GUID": "l1"}, {"@_NAME": "Loop B", "PARENT": "Loop A", "GUID": "l2"}]
RENAMED = {"@_NAME": "Purchases", "@_RESERVEDNAME": "Purchase", "PARENT": "Purchases", "GUID": "vt-r"}


def voucher(kind):
    return {"type": "VOUCHER", "data": {"VOUCHERTYPENAME": kind, "GUID": kind + str(id(kind))}}


def test_base_type_follows_reserved_names_and_parent_chains():
    bases = base_types([PURCHASE, GST, OLD, BRANCH, ORDER, JOURNAL, *LOOP, RENAMED])
    assert bases["purchase gst"] == "Purchase"
    assert bases["purchase gst mumbai"] == "Purchase"
    assert bases["purchase order"] == "Purchase Order"
    assert bases["purchases"] == "Purchase"
    assert bases["journal"] == "Journal"
    assert bases["loop a"] is None and bases["loop b"] is None


def test_candidates_are_active_purchase_types_with_observed_use():
    found = candidates([PURCHASE, GST, OLD, BRANCH, ORDER, JOURNAL],
                       [voucher("Purchase GST"), voucher("Purchase GST"), voucher("Purchase"), voucher("Journal")])
    assert [(c["name"], c["used"]) for c in found] == [
        ("Purchase", 1), ("Purchase GST", 2), ("Purchase GST Mumbai", 0)]
    assert found[1]["identity"] == {"NAME": "Purchase GST", "GUID": "vt-g", "PARENT": "Purchase", "ALTERID": " 5"}


def test_summary_preselects_the_most_used_type_only_without_a_tie():
    assert summary([PURCHASE, GST], [voucher("Purchase GST")])["default"] == "vt-g"
    assert summary([PURCHASE, GST], [voucher("Purchase GST"), voucher("Purchase")])["default"] is None
    assert summary([PURCHASE, GST], [])["default"] is None
    assert summary([GST, ORDER], [])["default"] == "vt-g"
    assert summary([ORDER], [])["candidates"] == []


def test_pin_uses_the_only_candidate_or_requires_an_explicit_choice():
    company = {"company": "Sachin Infra (2026-27)"}
    only = candidates([GST, OLD, ORDER], [])
    assert pin(company, only, None)["NAME"] == "Purchase GST"
    several = candidates([PURCHASE, GST], [])
    with pytest.raises(ValueError, match="Choose the purchase voucher type for Sachin Infra"):
        pin(company, several, None)
    assert pin(company, several, "vt-p")["GUID"] == "vt-p"
    for choice in ("vt-o", "vt-po", "unknown"):
        with pytest.raises(ValueError, match="no longer an active purchase voucher type"):
            pin(company, candidates([PURCHASE, GST, OLD, ORDER], []), choice)
    with pytest.raises(ValueError, match="has no active purchase voucher type"):
        pin(company, candidates([OLD, ORDER, JOURNAL], []), None)


def target(guid, *records):
    return {"company": guid.upper(), "references": {"company_guid": guid},
            "purchase_voucher_types": candidates(list(records), [])}


def test_locked_run_requires_its_company_to_resolve_and_ignores_others():
    scope = {"company_mode": "locked", "locked_company_guid": "a",
             "companies": [target("a", PURCHASE, GST), target("b", OLD)]}
    with pytest.raises(ValueError, match="Choose the purchase voucher type for A"):
        apply_choices(scope, {})
    apply_choices(scope, {"a": "vt-g"})
    assert scope["companies"][0]["voucher_type"]["NAME"] == "Purchase GST"
    assert "voucher_type" not in scope["companies"][1]
    assert scope["voucher_type_version"] == 1


def test_inferred_run_records_unresolved_companies_for_their_own_bills_only():
    scope = {"company_mode": "infer", "locked_company_guid": None,
             "companies": [target("a", PURCHASE, GST), target("b", GST)]}
    apply_choices(scope, {})
    assert "Choose the purchase voucher type for A" in scope["companies"][0]["voucher_type_error"]
    assert scope["companies"][1]["voucher_type"]["NAME"] == "Purchase GST"


@pytest.mark.parametrize("choices", [{"unknown-company": "vt-g"}, {"a": 5}, ["vt-g"], {"a": "x" * 201}])
def test_malformed_choices_are_rejected(choices):
    scope = {"company_mode": "infer", "locked_company_guid": None, "companies": [target("a", GST)]}
    with pytest.raises(ValueError, match="voucher type"):
        apply_choices(scope, choices)
