"""Thin OpenAI-hosted session adapter; no workflow-specific reasoning loop."""

import base64
import json
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from openai import NotFoundError, OpenAI

RESULT_PATH = "/workspace/outputs/result.json"


def reconcile_turn(session_id, *, client=None):
    """Recover a persisted session's single turn without sending new input."""
    turns = list(
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.turns.list(session_id)
    )
    if len(turns) != 1:
        raise ValueError("Saved session requires turn reconciliation.")
    return turns[0].id


def close_session(session_id, *, client=None):
    """Release the hosted environment after its result is durably stored."""
    # An earlier cleanup may have succeeded before its receipt was saved.
    with suppress(NotFoundError):
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.delete(session_id)


def execute(
    key,
    files,
    context,
    on_event,
    *,
    instructions,
    execution_instructions,
    model,
    packages,
    skill_files=None,
    skill_description=None,
    skill_name=None,
    result_path=RESULT_PATH,
    client=None,
    session_id=None,
    turn_id=None,
):
    """Persist IDs as events arrive and recover saved artifacts after a restart.

    The worker reconnects to a saved session rather than submitting the task twice.
    Results are accepted only from the completed turn's exact artifact path.
    """
    client = client or OpenAI(timeout=60, max_retries=0)
    if session_id:
        turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
        if turn.status in ("failed", "cancelled"):
            raise ValueError(f"Agent turn {turn.status}.")
        if turn.status == "completed":
            return read_result(client, session_id, turn_id, result_path=result_path)
        events = client.beta.agents.sessions.events.stream(session_id)
    else:
        uploaded = [
            {
                "type": "inline",
                "path": f"/workspace/inputs/{f['id']}{Path(f['path']).suffix.lower()}",
                "data": base64.b64encode(bytes(f["content"])).decode(),
            }
            for f in files
        ]
        uploaded.append(
            {
                "type": "inline",
                "path": "/workspace/context.json",
                "data": base64.b64encode(json.dumps(context).encode()).decode(),
            }
        )
        sizes = [len(base64.b64decode(f["data"])) for f in uploaded]
        if max(sizes) > 5 * 1024 * 1024 or sum(sizes) > 10 * 1024 * 1024:
            raise ValueError(
                "Selected files and catalog context exceed hosted upload limits. Select a smaller scope."
            )
        skill_zip = BytesIO()
        skill_name = skill_name or key
        with ZipFile(skill_zip, "w") as archive:
            for path, content in (skill_files or {"SKILL.md": instructions}).items():
                archive.writestr(f"{skill_name}/{path}", content)
        events = client.beta.agents.sessions.create(
            agent={"model": model, "instructions": instructions + "\n" + execution_instructions},
            environment={
                "type": "openai_hosted",
                "network": {"access": "disabled"},
                "packages": {"python": packages},
                "files": uploaded,
                "skills": [
                    {
                        "type": "inline",
                        "name": skill_name,
                        "description": skill_description
                        or instructions.split("description: ", 1)[1].splitlines()[0],
                        "source": {
                            "type": "base64",
                            "media_type": "application/zip",
                            "data": base64.b64encode(skill_zip.getvalue()).decode(),
                        },
                    }
                ],
            },
            input="Perform the workflow using /workspace/context.json and the supplied files. "
            f"Publish the required JSON at {result_path}. "
            "Read your saved JSON back and verify it before completing.",
            stream=True,
        )
    completed = False
    with events:
        for event in events:
            data = event.model_dump(mode="json")
            session_id = data.get("session_id", session_id)
            turn_id = data.get("turn_id", turn_id)
            on_event(event.type, session_id, turn_id)
            if event.type in (
                "agent.session.turn.failed",
                "agent.session.turn.cancelled",
                "agent.session.environment.failed",
            ):
                raise ValueError(
                    "The hosted workflow could not complete. Review the run and retry explicitly."
                )
            if event.type == "agent.session.turn.completed":
                completed = True
                break
    if not completed:
        turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
        if turn.status != "completed":
            raise ValueError(
                "Agent stream ended before completion; the saved session can be reconciled."
            )
    return read_result(client, session_id, turn_id, result_path=result_path)


def read_result(client, session_id, turn_id, *, result_path=RESULT_PATH):
    for artifact in client.beta.agents.sessions.artifacts.list(session_id):
        if artifact.turn_id == turn_id and artifact.path == result_path:
            content = client.beta.agents.sessions.artifacts.content(
                artifact.id, session_id=session_id
            ).content
            if len(content) > 5_000_000:
                raise ValueError("Workflow result exceeds the supported size.")
            return json.loads(content)
    raise ValueError("The completed turn did not publish the required result.json artifact.")
