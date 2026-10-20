"""Retiring discovery choices must not break already-pinned destination checks."""

import copy

import pytest

from minkops_platform.accounts.bills import validate_references
from minkops_platform.errors import ServiceError


def test_pinned_reference_receipt_requires_exact_scope_and_scalar_identity_fields():
    plan = {"company": "Test", "port": 9000, "categories": ["company"]}
    receipt = {
        "company": "Test",
        "port": 9000,
        "collections": [
            {
                "category": "company",
                "status": "ready",
                "count": 1,
                "fields": ["GUID", "NAME"],
                "records": [{"NAME": "Test", "GUID": "guid"}],
            }
        ],
    }
    validate_references(receipt, plan)
    for mutation in ("scope", "count", "record", "category"):
        changed = copy.deepcopy(receipt)
        collection = changed["collections"][0]
        if mutation == "scope":
            changed["company"] = "Another"
        elif mutation == "count":
            collection["count"] = 2
        elif mutation == "record":
            collection["records"][0]["AMOUNT"] = "10"
        else:
            collection["category"] = "ledgers"
        with pytest.raises(ServiceError):
            validate_references(changed, plan)
