"""Trusted client composition, separate from editable workflow preferences.

The registration caller selects a repository-owned solution, never a run's
client-supplied configuration. JSON Schema enforces the same restriction in
settings and launches; its annotation lets the shared UI explain disabled choices.

A solution's `enabled_tools` is the single switch for which business systems a
workspace uses. Workflow schemas declare which tools each option needs through
`x-option-tools`, so pausing a tool restricts every workflow consistently.
"""

import json
from copy import deepcopy
from dataclasses import replace

from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import validate


def bind_definition(definition, solution_id, *, repository_root=REPOSITORY_ROOT):
    root = repository_root / "solutions"
    directory = (root / solution_id).resolve()
    if not directory.is_relative_to(root.resolve()):
        raise ValueError("Solution policy must be repository-owned")
    policy_path = directory / "workflow-policy.json"
    if not policy_path.exists():
        return definition
    policy = json.loads(policy_path.read_text())
    enabled = policy.get("enabled_tools")
    if enabled is None:
        return definition
    if not isinstance(enabled, list) or not all(isinstance(tool, str) for tool in enabled):
        raise ValueError("Solution policy must list enabled tools")
    description = policy.get("workflows", {}).get(definition.metadata["key"], {}).get("description")
    schema = deepcopy(definition.tenant_schema)
    changed = False
    for spec in schema["properties"].values():
        needs = spec.get("x-option-tools")
        if not needs:
            continue
        if set(needs) != set(spec["enum"]):
            raise ValueError("Every option must declare the tools it needs")
        allowed = [option for option in spec["enum"] if set(needs[option]) <= set(enabled)]
        if allowed == spec["enum"]:
            continue
        if not allowed:
            raise ValueError("Solution policy disables every option of a workflow setting")
        spec["allOf"] = [{"enum": allowed}]
        spec["x-enabled-options"] = allowed
        if description:
            spec["description"] = description
        changed = True
    return replace(definition, tenant_schema=schema) if changed else definition


def validate_option(registered_schema, name, value):
    """Validate against trusted registration, not preferences from the request."""
    validate(registered_schema["properties"][name], value)


def validate_destination(registered_schema, output_mode):
    validate_option(registered_schema, "output_mode", output_mode)
