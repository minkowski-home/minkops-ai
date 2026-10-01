"""Compatibility imports for existing callers; no workbook implementation here."""

from minkops_connectors.excel import (
    MAX_CELLS,
    inspect_workbook,
    mapped_columns,
    mapping_bounds,
    open_workbook,
    sheet_records,
    value_json,
)
from minkops_platform.accounts.catalog import (
    CATALOG_SCHEMA,
    apply_records,
    business_schema,
    validate_catalog,
    validate_data,
)

__all__ = [
    "MAX_CELLS",
    "inspect_workbook",
    "mapped_columns",
    "mapping_bounds",
    "open_workbook",
    "sheet_records",
    "value_json",
    "CATALOG_SCHEMA",
    "apply_records",
    "business_schema",
    "validate_catalog",
    "validate_data",
]
