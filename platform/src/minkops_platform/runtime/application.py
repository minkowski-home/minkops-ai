"""Shared workflow dispatch and trusted execution policy.

Handlers are ordinary Python objects registered in application bootstrap. A
definition selects a known handler; customer/request strings never import code.
OpenAI retains ownership of reasoning and tool orchestration.
"""

from copy import deepcopy
from dataclasses import dataclass

from minkops_platform.workflow_policies import enforce_policies as enforce_policies
from minkops_platform.workflow_policies import validate_policies as validate_policies

LEGACY_BINDINGS = {
    "source-discovery": {"handler": "accounts.discovery", "presentation": "accounts-discovery"},
    "bill-entry": {"handler": "accounts.bill", "presentation": "accounts-bill"},
}
RESERVED = {
    "runtime_binding",
    "authorized_bindings",
    "execution_snapshot",
    "instructions_snapshot",
    "agent_output_schema",
    "file_provenance",
    "catalog_snapshot",
    "local_discovery_snapshot",
}


@dataclass(frozen=True)
class Binding:
    handler: str
    presentation: str


def binding_for(run):
    binding = run["config"].get("runtime_binding")
    if binding is None:
        binding = LEGACY_BINDINGS.get(run.get("workflow_key"))
    if not binding:
        raise ValueError("Run has no installed runtime binding.")
    return Binding(binding["handler"], binding.get("presentation", "proposal"))


def execution_config(definition, selections, *, binding=None, authorized_bindings=()):
    """Pin trusted dispatch and access alongside the existing complete skill bundle."""
    if RESERVED.intersection(selections):
        raise ValueError("Run configuration contains reserved runtime fields.")
    if definition.execution_snapshot is None:
        raise ValueError("This workflow has no hosted execution definition.")
    runtime = deepcopy(
        binding
        or {
            "handler": definition.metadata.get("handler", "skill.proposal"),
            "presentation": definition.metadata.get("presentation", "proposal"),
            "policies": [],
            "capabilities": definition.metadata.get("capabilities", []),
        }
    )
    get_handler(runtime["handler"])
    validate_policies(runtime.get("policies", []))
    # Capabilities declare needs. Only an adapter's authorized resource lookup
    # can produce bindings; declarations never grant network/tool permissions.
    granted = {item["capability"] for item in authorized_bindings}
    if not set(runtime.get("capabilities", [])).issubset(granted):
        raise ValueError("Workflow requires unavailable authorized capabilities.")
    return {
        **deepcopy(selections),
        "runtime_binding": runtime,
        "authorized_bindings": deepcopy(list(authorized_bindings)),
        "instructions_snapshot": definition.instructions,
        "agent_output_schema": definition.agent_output_schema,
        "execution_snapshot": deepcopy(definition.execution_snapshot),
    }


def get_handler(key):
    from .handlers import HANDLERS

    if key not in HANDLERS:
        raise ValueError("Workflow selects an unavailable execution handler.")
    return HANDLERS[key]


def process(connection, store, run, *, executor, close_session, cleanup=True):
    from . import lifecycle

    handler = get_handler(binding_for(run).handler)
    files, context, domain = handler.prepare(connection, run)
    if "authorized_bindings" in run["config"]:
        granted = {
            item["resource_id"]: item["sha256"]
            for item in run["config"]["authorized_bindings"]
            if item["capability"] == "files.snapshot"
        }
        if any(granted.get(str(file["id"])) != file["sha256"] for file in files):
            raise ValueError("Execution input differs from the run's authorized resource snapshot.")
    store.observe(connection, run, "executing", handler.executing_summary, 20)
    connection.commit()
    result = lifecycle.execute_proposal(connection, store, run, files, context, executor)
    result = handler.validate(run, files, context, domain, result)
    result = enforce_policies(run["config"], result)
    store.save_result(connection, run, result)
    handler.finish(connection, store, run, context, domain, result)
    connection.commit()
    if cleanup:
        lifecycle.close_run(connection, store, run, close_session=close_session)
