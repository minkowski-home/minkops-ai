"""GST identity must be deterministic before a permanent master is offered."""
import pytest

from minkops_platform.accounts.supplier_gst import gstin, jurisdiction


@pytest.mark.parametrize("value", ["27AAPFU0939F1ZV"])
def test_known_check_characters_and_pan_structure(value):
    assert gstin(value.lower()) == value


@pytest.mark.parametrize("value", ["", "27AAPFU0939F1ZA", "00AAPFU0939F1ZV", "99AAPFU0939F1ZV",
    "27AADDU0939F1ZV", "27AAPFU0939F0ZV", "27AAPFU0939F1XV", "27 AAPFU0939F1ZV", None, 123])
def test_malformed_state_pan_entity_or_checksum_is_rejected(value):
    with pytest.raises(ValueError): gstin(value)


@pytest.mark.parametrize("printed", ["Maharashtra (27)", "27 - Maharashtra", "Maharashtra - 27", "  Maharashtra  "])
def test_a_printed_jurisdiction_name_and_code_resolve_to_one_state(printed):
    assert jurisdiction(printed) == "Maharashtra"


@pytest.mark.parametrize("printed", ["Maharashtra (08)", "27 - Rajasthan", "Maharashtra / Rajasthan", "28", "unknown"])
def test_conflicting_unknown_or_obsolete_jurisdictions_are_refused(printed):
    with pytest.raises(ValueError):
        jurisdiction(printed)


@pytest.mark.parametrize("printed,canonical", [("Orissa (21)", "Odisha"), ("Pondicherry", "Puducherry"),
                                               ("Jammu & Kashmir (01)", "Jammu and Kashmir")])
def test_recognized_aliases_resolve_to_one_current_jurisdiction(printed, canonical):
    assert jurisdiction(printed) == canonical
