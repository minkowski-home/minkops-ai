"""Exception sheets use typed, durable outcomes rather than model prose."""
import codecs
import copy
import csv
import io

import pytest

from minkops_platform.accounts.bill_review import REASONS, TITLE_CODES, reason_sentence, review, export_csv
from minkops_platform.accounts.checks import EXCEPTION_LABELS
from minkops_platform.accounts.tally_writes import HOLD_TITLES, defer_input
from minkops_platform.errors import ServiceError


def mixed_run():
    def bill(status, number, **fields):
        return {"source_file_id": "multi", "status": status, "data": {
            "invoice_number": number, "vendor": "=SUM(A1:A2)", "date": "2026-10-02",
            "subtotal": -100, "tax": -18, "total": -118}, "company_name": "Test Company",
            "exception_codes": ["supplier_unresolved"], "findings": ["UNTRUSTED MODEL PROSE"], **fields}
    return {"id": "run", "state": "review", "workflow_key": "bill-entry", "config": {
        "file_provenance": [{"id": "multi", "path": "@multi.pdf"}, {"id": "blank", "path": "blank.pdf"}]},
        "result": {"records": [bill("saved", "S"), bill("duplicate", "D"), bill("held", "+H"),
            bill("held", "F", save_hold="Internal diagnostic"), bill("rejected", "N")],
            "unresolved": [], "deferred": [{"source_file_id": "blank", "code": "not_a_bill", "reason": "A quotation"}]}}


def test_every_typed_code_and_native_title_has_a_sentence():
    assert set(EXCEPTION_LABELS) | set(HOLD_TITLES) <= set(REASONS)
    titles = set(HOLD_TITLES.values()) | set(EXCEPTION_LABELS.values()) | {
        "Run stopped", "Save waiting", "Save interrupted", "PC unavailable", "Review in Tally",
        "Review written bill", "Missing supplier"}
    assert titles <= set(TITLE_CODES)
    for code in REASONS:
        sentence = reason_sentence({"exception_codes": [code], "data": {}, "findings": ["SECRET"]})
        assert sentence.strip() and sentence.endswith(".") and "SECRET" not in sentence
    for title in titles:
        assert reason_sentence({}, title=title).endswith(".")


def test_review_and_csv_are_exception_only_per_bill_with_shared_file_attention_id():
    run = mixed_run()
    before = copy.deepcopy(run)
    items = [{"id": "supplier-item", "event_key": "bill:run:multi:supplier", "status": "pending"},
             {"id": "bill-item", "event_key": "bill:run:multi:bill", "status": "pending"}]
    view = review(run, items)
    assert (view["saved"], view["duplicates"]) == (1, 1)
    assert [r["status"] for r in view["rows"]] == ["Needs attention", "Save held", "Not written (Do nothing)", "Not written (Do nothing)"]
    assert [r["attention_item_id"] for r in view["rows"][:3]] == ["bill-item"] * 3
    assert all(r["reason"] and "UNTRUSTED" not in r["reason"] for r in view["rows"])
    content = export_csv(run, items)
    assert content.startswith(codecs.BOM_UTF8)
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 4
    assert rows[0]["Source file"] == "'@multi.pdf"
    assert rows[0]["Invoice number"] == "'+H"
    assert rows[0]["Supplier"] == "'=SUM(A1:A2)"
    assert rows[0]["Amount before taxes"] == "-100"
    assert rows[0]["Tax"] == "-18"
    assert rows[0]["Total"] == "-118"
    assert run == before


@pytest.mark.parametrize("state", ["queued", "executing", "collecting", "writing"])
def test_export_refuses_an_unstable_snapshot(state):
    run = mixed_run(); run["state"] = state
    with pytest.raises(ServiceError, match="ready"):
        export_csv(run)


@pytest.mark.parametrize("state", ["review", "completed", "failed", "stopped"])
def test_stable_snapshot_exports(state):
    run = mixed_run(); run["state"] = state
    assert export_csv(run).startswith(codecs.BOM_UTF8)


def test_do_nothing_preserves_unresolved_code_and_reason():
    result = {"records": [], "unresolved": [{"source_file_id": "bill", "code": "not_a_bill", "reason": "Quotation"}]}
    defer_input(result, "bill")
    defer_input(result, "bill")
    assert result["deferred"] == [{"source_file_id": "bill", "code": "not_a_bill", "reason": "Quotation"}]
    assert result["unresolved"] == []


def test_text_controls_are_escaped_and_unknown_codes_have_a_deterministic_fallback():
    run = mixed_run()
    row = run["result"]["records"][2]
    row["data"]["invoice_number"] = "\t=cmd"
    row["exception_codes"] = ["future_code"]
    assert "'\t=cmd" in export_csv(run).decode("utf-8-sig")
    assert reason_sentence(row) == "This bill needs manual review in the original system."
