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
                "identity": {
                    "@_NAME": name,
                    "GUID": name + "-guid",
                    "COMPANYNUMBER": "100000" if name == "A" else "100001",
                },
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
        "company_scope": [
            {
                "company": c["company"],
                "company_guid": c["company_guid"],
                "company_number": str(100000 + index),
            }
            for index, c in enumerate(companies)
        ],
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
        lambda s: s.pop("company_scope"),
        lambda s: s["company_scope"].pop(),
        lambda s: s["company_scope"][0].update(company_guid="replacement"),
        lambda s: s.update(scope_error="Company scope changed."),
    ],
)
@pytest.mark.parametrize("factory", [lambda: snapshot(), lambda: open_snapshot()])
def test_invalid_snapshot_rejected(mutation, factory):
    value = factory()
    mutation(value)
    with pytest.raises(ValueError):
        validate_snapshot(
            value, {"port": 9000, "period": {"from": "2026-10-01", "to": "2026-10-02"}}
        )


def open_snapshot():
    """Format 3: the scope is the companies open in Tally, identified by GUID."""
    value = snapshot()
    value["format_version"] = "3"
    # Each data folder numbers its companies from 100000, so numbers repeat.
    for company in value["companies"]:
        company["identity"]["COMPANYNUMBER"] = " 100000"
    for entry in value["company_scope"]:
        entry["company_number"] = "100000"
    return value


def test_open_scope_allows_folder_local_numbers_to_repeat_or_be_absent():
    value = open_snapshot()
    validate_snapshot(value, {"port": 9000, "period": value["period"]})
    value["company_scope"][0]["company_number"] = None
    del value["companies"][0]["identity"]["COMPANYNUMBER"]
    validate_snapshot(value, {"port": 9000, "period": value["period"]})


def rename(value, index, name):
    value["company_scope"][index]["company"] = name
    value["companies"][index]["company"] = name
    value["companies"][index]["identity"]["@_NAME"] = name


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: rename(s, 1, "a"),  # Tally names are case-insensitive
        lambda s: s["company_scope"][0].update(company_guid=None),
        lambda s: s["company_scope"][0].update(company_number="10000x"),
        lambda s: s["company_scope"][0].update(extra="field"),
    ],
)
def test_open_scope_requires_unique_names_and_guids(mutation):
    value = open_snapshot()
    mutation(value)
    with pytest.raises(ValueError):
        validate_snapshot(value, {"port": 9000, "period": value["period"]})


def test_scope_failure_is_partial_even_when_every_export_succeeded():
    value = snapshot()
    value.update(partial=True, scope_error="Company scope changed. Refresh discovery.")
    validate_snapshot(value, {"port": 9000, "period": value["period"]})


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


def test_master_lookup_preserves_raw_evidence_and_indexes_company_scoped_candidates():
    from minkops_platform.accounts.client_context import master_lookup

    company = snapshot()["companies"][0]
    records = company["masters"]["records"]
    records.extend([
        copy.deepcopy(records[0]),
        {"type": "LEDGER", "data": {"@_NAME": "Supplier", "GUID": "002"}},
        {"type": "TAXUNIT", "data": {"GUID": "tax", "GSTREGNUMBER": "00123"}},
        {"type": "INCOMETAXSLAB", "data": {"GUID": "slab"}},
        {"type": "COMPANY", "data": {"REMOTECMPINFO.LIST": {
            "NAME": "A-guid", "REMOTECMPNAME": "A", "REMOTECMPSTATE": "State",
        }}},
    ])
    original = copy.deepcopy(company)
    lookup = master_lookup(company)
    assert company == original
    assert lookup["summary"] == {
        "exported_count": 7, "unique_count": 5, "duplicate_count": 1,
        "metadata_count": 1,
        "counts_by_type": {"LEDGER": 2, "VOUCHERTYPE": 1, "TAXUNIT": 1, "INCOMETAXSLAB": 1},
    }
    assert lookup["records"][0]["source_record_indexes"] == [0, 2]
    assert lookup["records"][0]["data"]["GSTDETAILS.LIST"]["PARTYGSTIN"] == "00123"
    assert lookup["by_type"]["LEDGER"]["by_name"]["Supplier"] == [0, 2]
    assert lookup["by_type"]["LEDGER"]["by_guid"]["001"] == [0]
    assert lookup["company_guid"] == "A-guid"


def test_master_lookup_rejects_conflicting_identity_and_foreign_metadata():
    from minkops_platform.accounts.client_context import master_lookup

    company = snapshot()["companies"][0]
    duplicate = copy.deepcopy(company["masters"]["records"][0])
    duplicate["data"]["PARENT"] = "Different"
    company["masters"]["records"].append(duplicate)
    with pytest.raises(ValueError, match="Conflicting master identity"):
        master_lookup(company)
    company["masters"]["records"][-1] = {
        "type": "COMPANY", "data": {"REMOTECMPINFO.LIST": {
            "NAME": "B-guid", "REMOTECMPNAME": "B",
        }},
    }
    with pytest.raises(ValueError, match="metadata company identity"):
        master_lookup(company)


def test_context_lookup_locations_resolve_exact_records_without_cross_company_merging():
    import json

    catalog = {"run_id": "run", "format_version": "2", "master_lookup_version": "1",
               "sources": [{"tool": "tally", "snapshot": snapshot()}]}
    files, manifest = context_assets(catalog)
    contents = {"/workspace/inputs/" + f["id"] + ".json": json.loads(f["content"]) for f in files}
    for company in manifest["companies"]:
        index = contents[company["master_lookup_path"]]
        assert index["company_guid"] == company["company_guid"]
        location = index["by_type"]["LEDGER"]["by_name"]["Supplier"][0]
        record = contents[location["path"]][location["offset"]]
        assert record["data"]["GUID"] == "001"
        assert record["source_record_indexes"] == [0]


def test_existing_pinned_catalog_retains_original_master_files():
    import json

    value = snapshot()
    catalog = {"run_id": "run", "format_version": "2",
               "sources": [{"tool": "tally", "snapshot": value}]}
    files, manifest = context_assets(catalog)
    assert all("master_lookup_path" not in c for c in manifest["companies"])
    masters = next(f for f in files if f["path"] == "company-0-masters-0.json")
    assert json.loads(masters["content"]) == value["companies"][0]["masters"]["records"]


def test_master_index_locations_survive_file_chunk_boundaries():
    import json

    value = snapshot()
    company = value["companies"][0]
    company["masters"]["records"] = [
        {"type": "CUSTOM", "data": {"GUID": str(i), "@_NAME": "Shared", "TEXT": "x" * 1_800_000}}
        for i in range(2)
    ]
    catalog = {"run_id": "run", "format_version": "2", "master_lookup_version": "1",
               "sources": [{"tool": "tally", "snapshot": value}]}
    files, manifest = context_assets(catalog)
    contents = {"/workspace/inputs/" + f["id"] + ".json": json.loads(f["content"]) for f in files}
    index = contents[manifest["companies"][0]["master_lookup_path"]]
    candidates = index["by_type"]["CUSTOM"]["by_name"]["Shared"]
    assert len({entry["path"] for entry in candidates}) == 2
    assert [contents[entry["path"]][entry["offset"]]["data"]["GUID"] for entry in candidates] == ["0", "1"]


def test_detail_summary_does_not_change_stored_catalog(monkeypatch):
    from minkops_platform.discovery import detail
    monkeypatch.setattr("minkops_platform.discovery.control_state", lambda *args: "active")
    monkeypatch.setattr("minkops_platform.discovery.scope_changes", lambda *args: None)

    value = snapshot()
    catalog = {"sources": [{"tool": "tally", "snapshot": value}], "partial": False}
    original = copy.deepcopy(catalog)
    row = {key: None for key in ("id", "task_id", "device_id", "config", "observations", "created_at")}
    row.update(tenant_id="tenant", catalog=catalog, mapping_run_id=None, state="completed", confirmed_at="now")
    result = detail(None, row)
    assert catalog == original
    assert result["catalog"]["sources"][0]["snapshot"]["companies"][0]["master_summary"]["unique_count"] == 2
    offered = result["catalog"]["sources"][0]["snapshot"]["companies"][0]["purchase_voucher_types"]
    assert [c["name"] for c in offered["candidates"]] == ["Purchase"]


def test_unknown_lookup_version_and_conflicting_write_references_are_rejected():
    with pytest.raises(ValueError, match="Unsupported master lookup version"):
        context_assets({"format_version": "2", "master_lookup_version": "future"})
    value = snapshot()
    record = copy.deepcopy(value["companies"][0]["masters"]["records"][0])
    record["data"]["PARENT"] = "Conflict"
    value["companies"][0]["masters"]["records"].append(record)
    with pytest.raises(ValueError, match="Conflicting master identity"):
        targets_from_snapshot(value, "device", "discovery")


def test_real_company_masters_are_not_mistaken_for_metadata():
    from minkops_platform.accounts.client_context import master_lookup

    company = snapshot()["companies"][0]
    company["masters"]["records"].append({"type": "COMPANY", "data": company["identity"]})
    lookup = master_lookup(company)
    assert lookup["summary"]["metadata_count"] == 0
    assert lookup["by_type"]["COMPANY"]["by_guid"]["A-guid"] == [2]


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


def test_compact_record_format_drops_empty_values_but_keeps_offsets_and_meaning():
    import json

    value = snapshot()
    record = value["companies"][0]["masters"]["records"][0]["data"]
    record.update({"NARRATION": "", "ADDRESS.LIST": [], "OPENINGBALANCE": 0, "ISDEEMEDPOSITIVE": "No",
                   "ALLOCATIONS.LIST": [{"LEDGERNAME": "", "AMOUNT": "0"}, {}]})
    plain = {"run_id": "run", "format_version": "2", "master_lookup_version": "1",
             "sources": [{"tool": "tally", "snapshot": value}]}
    compact = {**plain, "context_record_format": "1"}
    before, after = context_assets(plain)[0], context_assets(compact)[0]
    # Catalogs pinned before the format existed keep their exact authorized bytes.
    assert [f["sha256"] for f in before] == [f["sha256"] for f in context_assets(copy.deepcopy(plain))[0]]
    assert sum(len(f["content"]) for f in after) < sum(len(f["content"]) for f in before)
    masters = json.loads(next(f for f in after if f["path"] == "company-0-masters-lookup-v1-0.json")["content"])
    data = masters[0]["data"]
    assert "NARRATION" not in data and "ADDRESS.LIST" not in data
    assert (data["OPENINGBALANCE"], data["ISDEEMEDPOSITIVE"]) == (0, "No")
    assert data["ALLOCATIONS.LIST"] == [{"AMOUNT": "0"}, {}]
    assert len(masters) == len(json.loads(next(
        f for f in before if f["path"] == "company-0-masters-lookup-v1-0.json")["content"]))
