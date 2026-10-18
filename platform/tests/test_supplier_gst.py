"""GST identity must be deterministic before a permanent master is offered."""
import pytest

from minkops_platform.accounts.supplier_gst import gstin, state_name, validate_details


@pytest.mark.parametrize("value", ["27AAPFU0939F1ZV"])
def test_known_check_characters_and_pan_structure(value):
    assert gstin(value.lower()) == value


@pytest.mark.parametrize("value", ["", "27AAPFU0939F1ZA", "00AAPFU0939F1ZV", "99AAPFU0939F1ZV",
    "27AADDU0939F1ZV", "27AAPFU0939F0ZV", "27AAPFU0939F1XV", "27 AAPFU0939F1ZV", None, 123])
def test_malformed_state_pan_entity_or_checksum_is_rejected(value):
    with pytest.raises(ValueError): gstin(value)


def details():
    return {"gstin": "27AAPFU0939F1ZV", "registration_type": "Regular", "state_code": "27",
            "state": "Maharashtra", "place_of_supply": "Maharashtra", "address": ["Synthetic industrial road", "Pune"],
            "pincode": "411001", "evidence": [
                {"field": "gstin", "page": 1, "quote": "Supplier GSTIN 27AAPFU0939F1ZV"},
                {"field": "registration_type", "page": 1, "quote": "Registration: Regular"},
                {"field": "state", "page": 1, "quote": "Maharashtra 27"},
                {"field": "place_of_supply", "page": 1, "quote": "Place of supply Maharashtra"},
                {"field": "address", "page": 1, "quote": "Synthetic industrial road, Pune 411001"}]}


def test_valid_printed_details_are_canonical_and_do_not_invent_address_or_registration():
    value = validate_details(details(), company_state="Maharashtra", tax=18)
    assert value["gstin"] == "27AAPFU0939F1ZV"
    assert value["state"] == state_name("27")
    assert value["address"] == ["Synthetic industrial road", "Pune"]


@pytest.mark.parametrize("change", [
    {"state_code": "08"}, {"state": "Rajasthan"}, {"address": []}, {"evidence": []},
    {"registration_type": "Unregistered"}, {"registration_type": "Composition"}, {"pincode": "abc"},
])
def test_invalid_or_insufficient_printed_details_cannot_authorize_creation(change):
    with pytest.raises(ValueError): validate_details({**details(), **change}, company_state="Maharashtra", tax=18)


def test_cross_state_and_unconfirmed_company_state_require_manual_review_in_v1():
    for company_state in ("Rajasthan", None):
        with pytest.raises(ValueError): validate_details(details(), company_state=company_state, tax=18)


def creation_fixture():
    from minkops_platform.accounts.supplier_gst import creation_plan
    candidate = {"data": {"tax": 18, "date": "2026-10-02"}, "supplier_details": details()}
    candidate["supplier_details"]["gstin"] = "27AABCM1256F1ZR"
    candidate["supplier_details"]["evidence"][0]["quote"] = "Supplier GSTIN 27AABCM1256F1ZR"
    template = {"type": "LEDGER", "data": {"@_NAME": "Existing registered supplier", "GUID": "template-guid", "ALTERID": "12",
                "PARENT": "Sundry Creditors", "PARTYGSTIN": "27AAPFU0939F1ZV", "GSTREGISTRATIONTYPE": "Regular"}}
    selected = {"references": {"company_guid": "company"}}
    run = {"config": {"tally_target": {"supplier_creation_version": 1}, "source_catalog_snapshot": {"sources": [
        {"tool": "tally", "snapshot": {"companies": [{"company_guid": "company", "identity": {"STATENAME": "Maharashtra"},
          "masters": {"records": [template]}}]}}]}}}
    return creation_plan, run, candidate, selected


def test_creation_requires_same_company_registered_template_and_matching_full_discovery():
    create, run, record, selected = creation_fixture()
    plan = create(run, record, selected)
    assert plan["gstin"] == "27AABCM1256F1ZR" and plan["template"]["guid"] == "template-guid"
    run["config"]["source_catalog_snapshot"]["sources"][0]["snapshot"]["companies"][0]["masters"]["records"] = []
    with pytest.raises(ValueError, match="template"): create(run, record, selected)


def test_existing_gstin_under_another_name_blocks_creation_and_legacy_pins_stay_off():
    create, run, record, selected = creation_fixture()
    record["supplier_details"] = details()
    with pytest.raises(ValueError, match="already carries"): create(run, record, selected)
    run["config"]["tally_target"].pop("supplier_creation_version")
    with pytest.raises(ValueError, match="pinned"): create(run, record, selected)


def test_gst_readback_rejects_lost_registration_state_address_or_pin():
    from minkops_platform.accounts.supplier_gst import verified_supplier
    expected = validate_details(details(), company_state="Maharashtra", tax=18)
    master = {"GUID": "new", "PARENT": "Sundry Creditors", "PARTYGSTIN": expected["gstin"], "GSTREGISTRATIONTYPE": "Regular",
              "LEDSTATENAME": "Maharashtra", "PLACEOFSUPPLY": "Maharashtra", "PINCODE": "411001", "ADDRESS.LIST": {"ADDRESS": expected["address"]}}
    assert verified_supplier(master, expected)
    for key in ("PARTYGSTIN", "GSTREGISTRATIONTYPE", "LEDSTATENAME", "PLACEOFSUPPLY", "PINCODE", "ADDRESS.LIST"):
        assert not verified_supplier({k: v for k, v in master.items() if k != key}, expected)
