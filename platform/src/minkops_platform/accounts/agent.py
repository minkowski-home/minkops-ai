"""Accounts execution binding over the shared hosted runtime."""

from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.runtime.openai_hosted import close_session as close_session
from minkops_platform.runtime.openai_hosted import execute as hosted_execute
from minkops_platform.runtime.openai_hosted import read_result as read_result

MODEL = "gpt-6-luna"
WORKFLOWS = REPOSITORY_ROOT / "employees/accounts-desk/workflows"


def discovery_prompt():
    return (WORKFLOWS / "source-discovery/execution-instructions.md").read_text()


def bill_prompt():
    return (WORKFLOWS / "bill-entry/execution-instructions.md").read_text()


def execute(key, files, context, on_event, *, client=None, session_id=None, turn_id=None):
    instructions = (
        context["config"].get("instructions_snapshot") or (WORKFLOWS / key / "SKILL.md").read_text()
    )
    prompt = discovery_prompt() if key == "source-discovery" else bill_prompt()
    return hosted_execute(
        key,
        files,
        context,
        on_event,
        instructions=instructions,
        execution_instructions=prompt,
        model=MODEL,
        packages=["openpyxl", "pymupdf"],
        client=client,
        session_id=session_id,
        turn_id=turn_id,
    )
