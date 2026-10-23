"""The offline score must distinguish expected holds from missing results."""
from scripts.pr_infra_acceptance import grade

BILL = {"invoice_number": "UAT/TEST/1", "date": "02-Sep-2026", "total": "118"}


def record(**values):
    return {"document": {"number": "UAT/TEST/1", "date": "2026-09-02", "total": 118},
            "findings": [], "exception_codes": [], **values}


def test_happy_path_requires_one_correct_unheld_proposal():
    assert grade("B01", BILL, [record()], [])[0]
    assert not grade("B01", BILL, [], [])[0]
    assert not grade("B01", BILL, [record(), record()], [])[0]
    assert not grade("B01", BILL, [record(save_hold="Uncertain save")], [])[0]
    assert not grade("B01", {**BILL, "tax": "18"}, [record(data={"tax": 17})], [])[0]


def test_expected_negative_scenarios_never_pass_a_save_or_wrong_reason():
    assert grade("B06", BILL, [record(exception_codes=["source_values_conflict"])], [])[0]
    assert not grade("B06", BILL, [record(status="saved", exception_codes=["source_values_conflict"])], [])[0]
    assert not grade("B06", BILL, [record(exception_codes=["company_unresolved"])], [])[0]


def test_supplier_and_duplicate_tests_require_their_actual_user_outcomes():
    supplier = record(exception_codes=["supplier_missing"], allowed_actions=["nothing"])
    assert not grade("B03", BILL, [supplier], [])[0]
    supplier["allowed_actions"].append("supplier")
    assert grade("B03", BILL, [supplier], [])[0]
    assert grade("B04", BILL, [record(status="duplicate")], [])[0]
    assert not grade("B09", BILL, [record(status="saved")], [])[0]


def test_policy_holds_are_reported_explicitly_and_require_opt_in():
    held = record(exception_codes=["unsupported_structure"])
    assert not grade("B02", BILL, [held], [])[0]
    assert grade("B02", BILL, [held], [], allow_policy_holds=True)[0]
