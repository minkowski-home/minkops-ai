"""Definition-driven hosted execution; no employee-specific dispatch or tool loop."""

from .bundles import validate_snapshot
from .openai_hosted import execute as hosted_execute


def execute(key, files, context, on_event, *, client=None, session_id=None, turn_id=None):
    snapshot = validate_snapshot(context["config"]["execution_snapshot"])
    if snapshot["key"] != key:
        raise ValueError("Execution bundle does not belong to this workflow.")
    version = context.get("definition_version")
    if version is not None and version != snapshot["definition_version"]:
        raise ValueError("Execution bundle does not match the run's definition version.")
    execution = snapshot["execution"]
    return hosted_execute(
        key,
        files,
        context,
        on_event,
        instructions=snapshot["files"]["SKILL.md"],
        execution_instructions=snapshot["files"][execution["instructions"]],
        model=execution["model"],
        packages=execution["python_packages"],
        skill_files=snapshot["files"],
        skill_description=snapshot["description"],
        skill_name=snapshot["skill_name"],
        result_path=execution["result_path"],
        client=client,
        session_id=session_id,
        turn_id=turn_id,
    )
