"""GST identity must be deterministic before a permanent master is offered."""
import pytest

from minkops_platform.accounts.supplier_gst import gstin, jurisdiction, state_name, validate_details


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


@pytest.mark.parametrize("printed", ["Maharashtra (27)", "27 - Maharashtra", "Maharashtra - 27", "  Maharashtra  "])
def test_printed_jurisdiction_name_and_code_resolve_without_losing_evidence(printed):
    source = details()
    source["place_of_supply"] = printed
    source["evidence"][3]["quote"] = f"Place of supply: {printed}"
    assert validate_details(source, company_state="Maharashtra", tax=18)["place_of_supply"] == "Maharashtra"
    assert source["place_of_supply"] == printed


@pytest.mark.parametrize("printed", ["Maharashtra (08)", "27 - Rajasthan", "Maharashtra / Rajasthan", "28", "unknown"])
def test_conflicting_unknown_or_obsolete_jurisdictions_do_not_authorize_creation(printed):
    source = details()
    source["place_of_supply"] = printed
    source["evidence"][3]["quote"] = f"Place of supply: {printed}"
    with pytest.raises(ValueError):
        validate_details(source, company_state="Maharashtra", tax=18)


@pytest.mark.parametrize("printed,canonical", [("Orissa (21)", "Odisha"), ("Pondicherry", "Puducherry"),
                                               ("Jammu & Kashmir (01)", "Jammu and Kashmir")])
def test_recognized_aliases_resolve_to_one_current_jurisdiction(printed, canonical):
    assert jurisdiction(printed) == canonical


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
    printed = details()
    printed["gstin"] = "27AABCM1256F1ZR"
    printed["evidence"][0]["quote"] = "Supplier GSTIN 27AABCM1256F1ZR"
    template = {"type": "LEDGER", "data": {"@_NAME": "Existing registered supplier", "GUID": "template-guid", "ALTERID": "12",
                "PARENT": "Sundry Creditors", "PARTYGSTIN": "27AAPFU0939F1ZV", "GSTREGISTRATIONTYPE": "Regular"}}
    view = {"identity": {"STATENAME": "Maharashtra"}, "masters": {"records": [template]}}
    return printed, view


def test_creation_models_the_ledger_on_a_same_company_registered_creditor():
    from minkops_platform.accounts.supplier_gst import creation_plan
    printed, view = creation_fixture()
    plan = creation_plan(printed, view, tax=18, issued="2026-10-02")
    assert (plan["gstin"], plan["template"]["guid"], plan["applicable_from"]) == ("27AABCM1256F1ZR", "template-guid",
                                                                                  "2026-10-02")
    view["masters"]["records"] = []
    with pytest.raises(ValueError, match="model the new ledger on"):
        creation_plan(printed, view, tax=18, issued="2026-10-02")
    assert creation_plan(None, view, tax=0, issued="2026-10-02") is None
    with pytest.raises(ValueError, match="details are missing"):
        creation_plan(None, view, tax=18, issued="2026-10-02")


def test_existing_gstin_under_another_name_blocks_creation():
    from minkops_platform.accounts.supplier_gst import creation_plan
    _, view = creation_fixture()
    with pytest.raises(ValueError, match="already carries"):
        creation_plan(details(), view, tax=18, issued="2026-10-02")


def test_gst_readback_rejects_lost_registration_state_address_or_pin():
    from minkops_platform.accounts.supplier_gst import verified_supplier
    expected = validate_details(details(), company_state="Maharashtra", tax=18)
    master = {"GUID": "new", "PARENT": "Sundry Creditors", "PARTYGSTIN": expected["gstin"], "GSTREGISTRATIONTYPE": "Regular",
              "LEDSTATENAME": "Maharashtra", "PLACEOFSUPPLY": "Maharashtra", "PINCODE": "411001", "ADDRESS.LIST": {"ADDRESS": expected["address"]}}
    assert verified_supplier(master, expected)
    for key in ("PARTYGSTIN", "GSTREGISTRATIONTYPE", "LEDSTATENAME", "PLACEOFSUPPLY", "PINCODE", "ADDRESS.LIST"):
        assert not verified_supplier({k: v for k, v in master.items() if k != key}, expected)
