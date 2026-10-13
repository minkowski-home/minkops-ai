"""The typed agent contract decides what blocks a bill; observations never do."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator, ValidationError
from minkops_platform.accounts.attention import exception_label, issue_record
from minkops_platform.accounts.checks import EXCEPTION_LABELS, adopt_exceptions
from minkops_platform.resources import REPOSITORY_ROOT

SCHEMA = json.loads((REPOSITORY_ROOT / "employees/accounts-desk/workflows/bill-entry"
                     / "agent-output.schema.json").read_text())


def proposal(**record):
    return {"records": [{"source_file_id": "bill", "destination_file_id": "destination",
                         "sheet": "Purchase", "table": None, "operation": "append", "data": {},
                         "evidence": [], "exceptions": [], **record}],
            "exceptions": [], "unresolved": []}


def test_only_enumerated_exceptions_block_and_notes_stay_internal():
    notes = ["Arithmetic reconciles.", "Possibly MOCK-1 again; the native check decides."]
    result = proposal(exceptions=[{"code": "classification_uncertain", "detail": "Two expense ledgers fit."}],
                      notes=notes)
    Draft202012Validator(SCHEMA).validate(result)
    adopted = adopt_exceptions(result)
    record = adopted["records"][0]
    assert record["findings"] == ["Two expense ledgers fit."]
    assert record["exception_codes"] == ["classification_uncertain"]
    assert record["notes"] == notes
    assert "exceptions" not in record and "exceptions" not in adopted
    assert adopted["findings"] == [] and adopted["exception_codes"] == []


def test_a_bill_with_only_observations_has_nothing_blocking():
    adopted = adopt_exceptions(proposal(notes=["Optional cost code absent."]))
    assert adopted["records"][0]["findings"] == []


def test_contract_rejects_free_text_findings_and_unlisted_codes():
    for invalid in (proposal(findings=["anything"]),
                    proposal(exceptions=[{"code": "possible_duplicate", "detail": "Similar bill."}]),
                    proposal(exceptions=[{"code": "source_unreadable", "detail": ""}])):
        with pytest.raises(ValidationError):
            Draft202012Validator(SCHEMA).validate(invalid)


def test_unresolved_inputs_keep_codes_and_pinned_legacy_results_pass_through():
    result = {"records": [], "exceptions": [], "unresolved": [
        {"source_file_id": "bill", "code": "source_unreadable", "reason": "Blank page."}]}
    Draft202012Validator(SCHEMA).validate(result)
    adopted = adopt_exceptions(result)
    assert issue_record(adopted, adopted["unresolved"][0])["exception_codes"] == ["source_unreadable"]
    legacy = {"records": [{"source_file_id": "bill", "findings": ["old"]}], "findings": []}
    assert adopt_exceptions(copy.deepcopy(legacy)) == legacy


def test_labels_come_from_codes_and_every_listed_code_has_one():
    record = {"exception_codes": ["supplier_missing"], "findings": ["Buyer company text."]}
    assert exception_label(record) == "Missing supplier"
    codes = SCHEMA["$defs"]["exception_code"]["enum"]
    assert set(codes) == set(EXCEPTION_LABELS)
