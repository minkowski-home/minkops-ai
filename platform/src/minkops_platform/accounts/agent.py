"""Accounts execution binding over the shared hosted runtime."""

from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.runtime.openai_hosted import close_session as close_session
from minkops_platform.runtime.openai_hosted import execute as hosted_execute
from minkops_platform.runtime.openai_hosted import read_result as read_result
from minkops_platform.runtime.workflow import execute as workflow_execute
from minkops_platform.workflows import load_definition

WORKFLOWS = REPOSITORY_ROOT / "employees/accounts-desk/workflows"
# Compatibility export for earlier callers; execution uses the pinned descriptor.
MODEL = "gpt-6-luna"


def discovery_prompt():
    return (WORKFLOWS / "source-discovery/execution-instructions.md").read_text()


def bill_prompt():
    return (WORKFLOWS / "bill-entry/execution-instructions.md").read_text()


def execute(key, files, context, on_event, *, client=None, session_id=None, turn_id=None):
    if context["config"].get("execution_snapshot"):
        return workflow_execute(
            key, files, context, on_event, client=client, session_id=session_id, turn_id=turn_id
        )
    if not session_id:
        # Direct callers may use the current definition. Durable workers require
        # a launch-time snapshot; legacy active sessions only reconcile below.
        definition = load_definition(WORKFLOWS / key)
        bound_context = {
            **context,
            "config": {**context["config"], "execution_snapshot": definition.execution_snapshot},
        }
        return workflow_execute(key, files, bound_context, on_event, client=client)
    # Legacy sessions already have their instructions and environment. Recovery
    # must not reread a newer checkout, create a session, or send another input.
    return hosted_execute(
        key,
        files,
        context,
        on_event,
        instructions="",
        execution_instructions="",
        model="",
        packages=[],
        client=client,
        session_id=session_id,
        turn_id=turn_id,
    )
