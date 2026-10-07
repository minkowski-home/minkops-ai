"""Trusted client composition, separate from editable workflow preferences.

The registration caller selects a repository-owned solution, never a run's
client-supplied configuration. JSON Schema enforces the same restriction in
settings and launches; its annotation lets the shared UI explain disabled choices.
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
    policy = json.loads(policy_path.read_text()).get(definition.metadata["key"], {})
    if not policy:
        return definition
    allowed = policy["allowed_output_modes"]
    schema = deepcopy(definition.tenant_schema)
    spec = schema["properties"]["output_mode"]
    if not allowed or not set(allowed).issubset(spec["enum"]):
        raise ValueError("Solution policy contains unsupported destinations")
    spec["allOf"] = [{"enum": allowed}]
    spec["x-enabled-options"] = allowed
    spec["description"] = policy.get("description", spec.get("description", ""))
    return replace(definition, tenant_schema=schema)


def validate_destination(registered_schema, output_mode):
    """Validate against trusted registration, not preferences from the request."""
    validate(registered_schema["properties"]["output_mode"], output_mode)
