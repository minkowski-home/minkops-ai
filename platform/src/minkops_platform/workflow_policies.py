"""Deterministic client policies selected by trusted installation bindings.

Add a schema and ordinary Python check to the explicit registry. Tenant data
cannot dynamically import Python. Checks return a review requirement and never
perform destination writes themselves.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class Policy:
    schema: dict
    check: Callable[[dict, dict], bool]


def review_threshold(spec, result):
    required = False
    for record in result.get("records", []):
        raw = record.get("data", {}).get(spec["field"])
        try:
            if raw is None or isinstance(raw, bool):
                raise ValueError("Missing numeric policy field.")
            value = Decimal(str(raw))
            if not value.is_finite():
                raise ValueError("Policy field must be finite.")
            required |= value > Decimal(str(spec["amount"]))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Client review policy requires a valid numeric amount.") from error
    return required


POLICIES = {
    "review-threshold": Policy(
        {
            "type": "object",
            "required": ["field", "amount"],
            "additionalProperties": False,
            "properties": {
                "field": {"type": "string", "minLength": 1},
                "amount": {"type": "number", "minimum": 0},
            },
        },
        review_threshold,
    ),
}


def validate_policies(policies):
    Draft202012Validator(
        {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "config"],
                "additionalProperties": False,
                "properties": {
                    "key": {"type": "string", "enum": list(POLICIES)},
                    "config": {"type": "object"},
                },
            },
        }
    ).validate(policies)
    for selected in policies:
        Draft202012Validator(POLICIES[selected["key"]].schema).validate(selected["config"])


def enforce_policies(config, result):
    checked = deepcopy(result)
    policies = config.get("runtime_binding", {}).get("policies", [])
    validate_policies(policies)
    for selected in policies:
        required = POLICIES[selected["key"]].check(selected["config"], checked)
        checked["requires_review"] = bool(checked.get("requires_review", False) or required)
    return checked
