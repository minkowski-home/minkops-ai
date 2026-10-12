"""Complete discovery is the only launch contract; depth is not a preference."""

import pytest
from jsonschema import Draft202012Validator, ValidationError
from minkops_platform.discovery import CONFIG_SCHEMA
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import load_definition


def test_depth_is_absent_from_settings_and_hosted_run_options():
    definition = load_definition(
        REPOSITORY_ROOT / "employees/accounts-desk/workflows/source-discovery"
    )
    assert "discovery_depth" not in definition.tenant_schema["properties"]
    assert "discovery_depth" not in definition.run_schema["properties"]
    assert "discovery_depth" not in definition.metadata["tenant_defaults"]


@pytest.mark.parametrize("depth", ["structure", "reference_data", "business_mappings"])
def test_obsolete_native_depths_are_rejected(depth):
    with pytest.raises(ValidationError):
        Draft202012Validator(CONFIG_SCHEMA).validate(
            {
                "depth": depth,
                "excel_source_ids": [],
                "tally": {"port": 9000, "period": {"from": "2026-10-01", "to": "2026-10-02"}},
            }
        )
