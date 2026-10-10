"""Client discovery evidence is pinned; routing never guesses a company."""

import copy
import pytest
from minkops_platform.accounts.client_context import (
    validate_snapshot,
    targets_from_snapshot,
    select_target,
    context_assets,
)


def snapshot():
    companies = []
    for name in ("A", "B"):
        companies.append(
            {
                "company": name,
                "company_guid": name + "-guid",
                "port": 9000,
                "status": "ready",
                "identity": {"@_NAME": name, "GUID": name + "-guid"},
                "masters": {
                    "status": "ready",
                    "count": 2,
                    "records": [
                        {
                            "type": "LEDGER",
                            "data": {
                                "@_NAME": "Supplier",
                                "GUID": "001",
                                "PARENT": "Sundry Creditors",
                                "GSTDETAILS.LIST": {"PARTYGSTIN": "00123"},
                            },
                        },
                        {"type": "VOUCHERTYPE", "data": {"@_NAME": "Purchase"}},
                    ],
                },
                "vouchers": {
                    "status": "ready",
                    "count": 1,
                    "records": [{"type": "VOUCHER", "data": {"GUID": "v1", "DATE": "20261001"}}],
                },
            }
        )
    return {
        "format_version": "2",
        "period": {"from": "2026-10-01", "to": "2026-10-02"},
        "companies": companies,
        "partial": False,
    }


def test_full_nested_records_preserved_and_undated_masters():
    value = snapshot()
    validate_snapshot(value, {"port": 9000, "period": value["period"]})
    assert (
        value["companies"][0]["masters"]["records"][0]["data"]["GSTDETAILS.LIST"]["PARTYGSTIN"]
        == "00123"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s["companies"].append(copy.deepcopy(s["companies"][0])),
        lambda s: s["companies"][0]["vouchers"]["records"][0]["data"].update(DATE="20260930"),
        lambda s: s["companies"][0]["masters"].update(count=1),
        lambda s: s["companies"][0].update(company_guid="different"),
        lambda s: s["companies"][0].update(port=9001),
        lambda s: s.update(partial=True),
        lambda s: s["companies"].__setitem__(0, "invalid"),
    ],
)
def test_invalid_snapshot_rejected(mutation):
    value = snapshot()
    mutation(value)
    with pytest.raises(ValueError):
        validate_snapshot(
            value, {"port": 9000, "period": {"from": "2026-10-01", "to": "2026-10-02"}}
        )


def test_explicit_company_per_record_and_locked_mode():
    targets = targets_from_snapshot(snapshot(), "device", "discovery")
    run_target = {"companies": targets, "company_mode": "infer", "locked_company_guid": None}
    assert (
        select_target(
            {"company_guid": "B-guid", "company_evidence": "Buyer matches B"}, run_target
        )["company"]
        == "B"
    )
    with pytest.raises(ValueError):
        select_target({}, run_target)
    with pytest.raises(ValueError):
        select_target({"company_guid": "unknown", "company_evidence": "Buyer"}, run_target)
    run_target.update(company_mode="locked", locked_company_guid="A-guid")
    assert select_target({}, run_target)["company"] == "A"
    with pytest.raises(ValueError):
        select_target({"company_guid": "B-guid", "company_evidence": "Buyer matches B"}, run_target)


def test_context_assets_are_pinned_separate_files_with_stable_hashes():
    catalog = {
        "run_id": "run",
        "format_version": "2",
        "sources": [{"tool": "tally", "snapshot": snapshot()}],
        "context_notes": [],
    }
    files, manifest = context_assets(catalog)
    assert len(files) >= 4
    assert all("content" in f and "sha256" in f for f in files)
    assert "records" not in str(manifest)
    assert [f["sha256"] for f in files] == [f["sha256"] for f in context_assets(catalog)[0]]


def test_inferred_company_without_evidence_cannot_reach_write_selection():
    target = {
        "companies": targets_from_snapshot(snapshot(), "device", "discovery"),
        "company_mode": "infer",
    }
    with pytest.raises(ValueError, match="evidence"):
        select_target({"company_guid": "A-guid", "company_evidence": "  "}, target)


def test_context_notes_require_actual_collected_evidence():
    from minkops_platform.accounts.client_context import validate_notes

    catalog = {"sources": [{"tool": "tally", "snapshot": snapshot()}]}
    note = {
        "company_guid": "A-guid",
        "observation": "An obscure convention",
        "evidence_ids": ["001"],
        "certainty": "inferred",
    }
    assert validate_notes([note], catalog) == [note]
    with pytest.raises(ValueError, match="evidence"):
        validate_notes([{**note, "evidence_ids": ["invented"]}], catalog)
    with pytest.raises(ValueError, match="undiscovered"):
        validate_notes([{**note, "company_guid": "unknown"}], catalog)
