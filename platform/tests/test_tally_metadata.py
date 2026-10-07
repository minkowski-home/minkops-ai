"""Real Tally ODBC metadata may expose one method at different positions."""

import pytest

from minkops_platform.discovery import _validate_columns
from minkops_platform.errors import ServiceError


def test_repeated_method_names_preserve_distinct_odbc_positions():
    # Observed in CostCentreBreakUp and AllCostCentre on the release test PC.
    columns = [
        {"name": "$Category", "ordinal": 18, "type": "VarChar", "nullable": True},
        {"name": "$Category", "ordinal": 78, "type": "VarChar", "nullable": True},
    ]
    _validate_columns(columns)
    assert [column["ordinal"] for column in columns] == [18, 78]


def test_two_columns_cannot_claim_the_same_odbc_position():
    columns = [
        {"name": "$Category", "ordinal": 18, "type": "VarChar", "nullable": True},
        {"name": "$Other", "ordinal": 18, "type": "VarChar", "nullable": True},
    ]
    with pytest.raises(ServiceError, match="Duplicate Tally metadata"):
        _validate_columns(columns)
