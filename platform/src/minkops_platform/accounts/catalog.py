"""Accounts catalog and business record validation against confirmed mappings."""

import json

from jsonschema import Draft202012Validator, FormatChecker
from minkops_connectors.excel import apply_records as write_records
from minkops_connectors.excel import mapping_bounds, open_workbook

from minkops_platform.resources import REPOSITORY_ROOT

CATALOG_SCHEMA = json.loads(
    (
        REPOSITORY_ROOT
        / "employees/accounts-desk/workflows/source-discovery/agent-output.schema.json"
    ).read_text()
)


def validate_catalog(catalog, contents, *, review_proposal=False):
    Draft202012Validator(CATALOG_SCHEMA).validate(catalog)
    seen = set()
    for mapping in catalog["sheets"]:
        identity = (mapping["file_id"], mapping["sheet"], mapping.get("table"))
        if identity in seen or mapping["file_id"] not in contents:
            raise ValueError("Catalog contains duplicate or unauthorized sheets.")
        seen.add(identity)
        w = open_workbook(contents[mapping["file_id"]])
        if mapping["sheet"] not in w.sheetnames:
            raise ValueError("Catalog refers to a missing worksheet.")
        s = w[mapping["sheet"]]
        a, b, c, d = mapping_bounds(s, mapping)
        headers = [
            str(s.cell(b, i).value).strip() if s.cell(b, i).value is not None else ""
            for i in range(a, c + 1)
        ]
        names = [c["name"] for c in mapping["columns"]]
        if not names and mapping["role"] != "ignore":
            raise ValueError("Reference and destination sheets require mapped columns.")
        if len(names) != len(set(names)) or any(headers.count(name) != 1 for name in names):
            raise ValueError("Each mapped column must match one real header.")
        if not set(mapping["key_columns"]).issubset(names):
            raise ValueError("Record keys must use mapped columns.")
        if mapping["role"] == "destination" and not mapping["key_columns"]:
            raise ValueError(
                "Destination sheets need record keys for duplicate detection and edits."
            )
        concepts = [c["concept"] for c in mapping["columns"] if c["concept"]]
        if not review_proposal and len(concepts) != len(set(concepts)):
            raise ValueError("Business concepts must map to unique columns within a sheet.")


def business_schema(mapping):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {c["name"]: {"type": [c["type"], "null"]} for c in mapping["columns"]},
        "required": [c["name"] for c in mapping["columns"] if c["required"]],
    }


def validate_data(mapping, data):
    errors = list(
        Draft202012Validator(business_schema(mapping), format_checker=FormatChecker()).iter_errors(
            data
        )
    )
    if errors:
        raise ValueError(errors[0].message)
    for c in mapping["columns"]:
        v = data.get(c["name"])
        if c["required"] and (v is None or v == ""):
            raise ValueError(f"{c['name']} requires a value.")
        if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")):
            raise ValueError(f"{c['name']} contains unsafe formula-like text.")


def apply_records(content, mapping, records):
    """Apply an Accounts plan using the generic Excel adapter and confirmed rules."""
    return write_records(content, mapping, records, validate_record=validate_data)
