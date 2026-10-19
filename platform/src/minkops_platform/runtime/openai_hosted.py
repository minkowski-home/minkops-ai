"""Thin OpenAI-hosted session adapter; no workflow-specific reasoning loop."""

import base64
import hashlib
import json
import time
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from openai import APIError, NotFoundError, OpenAI

RESULT_PATH = "/workspace/outputs/result.json"
# Long turns outlive individual provider streams; re-reading a turn is free.
STREAM_REATTACHMENTS = 3
REATTACH_DELAY = 2


def workspace_inputs(files, context, root="/workspace"):
    """Bind execution paths without changing any uploaded business evidence."""
    paths = {f"/workspace/inputs/{f['id']}{Path(f['path']).suffix.lower()}":
             f"{root}/inputs/{f['id']}{Path(f['path']).suffix.lower()}" for f in files}
    hashes = {}

    def bind(value):
        if isinstance(value, list):
            return [bind(item) for item in value]
        if isinstance(value, dict):
            result = {key: paths.get(item, item) if key in ("path", "master_lookup_path")
                      and isinstance(item, str) else bind(item) for key, item in value.items()}
            if isinstance(value.get("path"), str) and value["path"] in hashes and "sha256" in value:
                result["sha256"] = hashes[value["path"]]
            return result
        return value

    uploaded = []
    for file in files:
        original = f"/workspace/inputs/{file['id']}{Path(file['path']).suffix.lower()}"
        content = bytes(file["content"])
        if root != "/workspace" and file.get("workspace_references"):
            content = json.dumps(bind(json.loads(content)), sort_keys=True, ensure_ascii=False).encode()
            hashes[original] = hashlib.sha256(content).hexdigest()
        uploaded.append({"type": "inline", "path": paths[original],
                         "data": base64.b64encode(content).decode()})
    return uploaded, bind(context)


def skill_configuration(name, description, files):
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        for path, content in files.items():
            archive.writestr(f"{name}/{path}", content)
    return [{"type": "inline", "name": name, "description": description,
             "source": {"type": "base64", "media_type": "application/zip",
                        "data": base64.b64encode(archive_bytes.getvalue()).decode()}}]


def reconcile_turn(session_id, *, client=None):
    """Recover a persisted session's single turn without sending new input."""
    turns = list(
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.turns.list(session_id)
    )
    if len(turns) != 1:
        raise ValueError("Saved session requires turn reconciliation.")
    return turns[0].id


def close_session(session_id, *, client=None):
    """Detach this conversation after its result is durably stored."""
    # An earlier cleanup may have succeeded before its receipt was saved.
    with suppress(NotFoundError):
        (client or OpenAI(timeout=30, max_retries=0)).beta.agents.sessions.delete(session_id)


def cancel_turn(session_id, turn_id=None, *, client=None):
    """Cancel execution while preserving work; closing an SSE observer is insufficient."""
    client = client or OpenAI(timeout=15, max_retries=0)
    with suppress(NotFoundError):
        if turn_id and client.beta.agents.sessions.turns.retrieve(turn_id,session_id=session_id).status in ('completed','failed','cancelled'):
            return
        client.beta.agents.sessions.events.create(session_id,events=[{'type':'agent.session.input.cancel'}])


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
    environment_lease=None,
    workspace=None,
):
    """Persist IDs as events arrive and recover saved artifacts after a restart.

    The worker reconnects to a saved session rather than submitting the task twice.
    Results are accepted only from the completed turn's exact artifact path.
    """
    client = client or OpenAI(timeout=60, max_retries=0)
    workspace = workspace or context.get("config", {}).get("hosted_workspace")
    if workspace:
        result_path = workspace["result_path"]
    if session_id:
        turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
        if turn.status in ("failed", "cancelled"):
            raise ValueError(f"Agent turn {turn.status}.")
        if turn.status == "completed":
            return read_result(client, session_id, turn_id, result_path=result_path)
        events = client.beta.agents.sessions.events.stream(session_id)
    else:
        root = environment_lease.workspace["root"] if environment_lease else "/workspace"
        uploaded, bound_context = workspace_inputs(files, context, root)
        uploaded.append(
            {
                "type": "inline",
                "path": root + "/context.json",
                "data": base64.b64encode(json.dumps(bound_context).encode()).decode(),
            }
        )
        sizes = [len(base64.b64decode(f["data"])) for f in uploaded]
        if max(sizes) > 5 * 1024 * 1024 or sum(sizes) > 10 * 1024 * 1024:
            raise ValueError(
                "Selected files and catalog context exceed hosted upload limits. Select a smaller scope."
            )
        skill_name = skill_name or key
        skill_description = skill_description or instructions.split("description: ", 1)[1].splitlines()[0]
        skill_files = skill_files or {"SKILL.md": instructions}
        environment = {"type": "openai_hosted", "network": {"access": "disabled"},
                       "packages": {"python": packages}, "files": uploaded,
                       "skills": skill_configuration(skill_name, skill_description, skill_files)}
        if environment_lease:
            result_path = environment_lease.workspace["result_path"]

            def bind_instructions(text):
                return text.replace("/workspace/outputs/", "/workspace/outputs/" + root.rsplit("/", 1)[-1] + "/").replace(
                    "/workspace/context.json", root + "/context.json").replace("/workspace/inputs/", root + "/inputs/")

            instructions, execution_instructions = map(bind_instructions, (instructions, execution_instructions))
            skill_root = f"{root}/skills/{skill_name}"
            # Native skill routing is stable; the full pinned procedure/resources
            # are fresh per run, including any scripts with absolute input paths.
            routing = f"---\nname: {skill_name}\ndescription: {json.dumps(skill_description)}\n---\n" + (
                "Follow the complete pinned workflow skill at the path specified in this session's input. "
                "Use that run's resources and context exclusively; do not use previous runs' files.\n")
            environment_id = environment_lease.prepare(client, {
                "type": "openai_hosted", "network": {"access": "disabled"},
                "packages": {"python": packages},
                "skills": skill_configuration(skill_name, skill_description, {"SKILL.md": routing}),
            })
            for path, content in skill_files.items():
                uploaded.append({"type": "inline", "path": f"{skill_root}/{path}",
                                 "data": base64.b64encode(bind_instructions(content).encode()).decode()})
            for file in uploaded:
                client.beta.agents.environments.files.create(environment_id, **file)
            environment_lease.check_start()
            environment = {"type": "openai_hosted", "environment_id": environment_id}
            execution_instructions += f"\nWorkflow resources and working directory: {skill_root}."
        events = client.beta.agents.sessions.create(
            agent={"model": model, "instructions": instructions + "\n" + execution_instructions},
            environment=environment,
            input=f"Perform the workflow using {root}/context.json and the supplied files. "
            + (f"Read {skill_root}/SKILL.md and its supporting resources first. " if environment_lease else "")
            + f"Publish the required JSON at {result_path}. "
            "Read your saved JSON back and verify it before completing.",
            stream=True,
        )
    completed = False
    for attempt in range(STREAM_REATTACHMENTS + 1):
        try:
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
            break
        except APIError:
            # The SDK raises transport and timeout failures as APIError subclasses.
            # A dropped stream does not end the turn. Once the turn exists its
            # events can be re-read, so no session or input is ever resubmitted.
            # Before then, creation is ambiguous and stays an explicit retry.
            if not (session_id and turn_id) or attempt == STREAM_REATTACHMENTS:
                raise
            time.sleep(REATTACH_DELAY * (attempt + 1))
            turn = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
            if turn.status in ("failed", "cancelled"):
                raise ValueError(f"Agent turn {turn.status}.") from None
            if turn.status == "completed":
                completed = True
                break
            events = client.beta.agents.sessions.events.stream(session_id)
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
