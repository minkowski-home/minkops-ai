"""Repository-owned execution bundles, pinned before a hosted run is queued.

Explicit resource lists avoid uploading a directory's credentials or eval answers.
The digest detects revision drift; authorization still comes from application state.
"""

import hashlib
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

EXECUTION_SCHEMA = {
    "type": "object",
    "required": [
        "environment",
        "model",
        "python_packages",
        "instructions",
        "resources",
        "result_path",
    ],
    "additionalProperties": False,
    "properties": {
        "environment": {"const": "openai_hosted"},
        "model": {"type": "string", "minLength": 1},
        "python_packages": {
            "type": "array",
            "maxItems": 30,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "instructions": {"type": "string", "minLength": 1},
        "resources": {
            "type": "array",
            "maxItems": 100,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "result_path": {"type": "string", "minLength": 1},
    },
}


# Tool-session workflows run without an execution environment: what they pin
# is their model and the texts the sessions are instructed with, nothing that
# executes. `stages` names each further kind of session beside the main one.
SESSIONS_SCHEMA = {
    "type": "object",
    "required": ["model"],
    "additionalProperties": False,
    "properties": {
        "model": {"type": "string", "minLength": 1},
        "reasoning_effort": {"enum": ["low", "medium", "high"]},
        "stages": {
            "type": "object",
            "maxProperties": 10,
            "propertyNames": {"pattern": "^[a-z][a-z_]{0,30}$"},
            "additionalProperties": {"type": "string", "minLength": 1},
        },
    },
}


def relative_path(value):
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(
            "Execution resources must use relative paths inside the workflow directory."
        )
    return value


def read_resource(directory: Path, value: str):
    path = directory / relative_path(value)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != directory):
        raise ValueError("Execution resources cannot follow symlinks.")
    if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError("Execution resources must be files inside the workflow directory.")
    if path.stat().st_size > 1_000_000:
        raise ValueError("Execution resource exceeds the supported size.")
    return path.read_text(encoding="utf-8")


def digest(snapshot):
    content = {key: value for key, value in snapshot.items() if key != "sha256"}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def skill_manifest(instructions):
    parts = instructions.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("Workflow skills require YAML frontmatter.")
    manifest = yaml.safe_load(parts[1])
    if not isinstance(manifest, dict):
        raise ValueError("Workflow skill manifest must be an object.")
    name, description = manifest.get("name"), manifest.get("description")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        raise ValueError("Workflow skill name must be a valid lowercase slug.")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Workflow skill description must be nonempty text.")
    return name, description


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("format_version") != 1:
        raise ValueError("Unsupported execution bundle format.")
    if snapshot.get("sha256") != digest(snapshot):
        raise ValueError("Execution bundle digest does not match its pinned content.")
    Draft202012Validator(EXECUTION_SCHEMA).validate(snapshot["execution"])
    output = snapshot["execution"]["result_path"]
    if not output.startswith("/workspace/outputs/"):
        raise ValueError("Execution output must stay inside /workspace/outputs.")
    relative_path(output.removeprefix("/workspace/outputs/"))
    files = snapshot["files"]
    for name, content in files.items():
        relative_path(name)
        if not isinstance(content, str) or len(content.encode()) > 1_000_000:
            raise ValueError("Execution resource exceeds the supported size.")
    if sum(len(content.encode()) for content in files.values()) > 5_000_000:
        raise ValueError("Execution bundle exceeds the supported size.")
    for name in (
        "SKILL.md",
        snapshot["execution"]["instructions"],
        *snapshot["execution"]["resources"],
    ):
        if name not in files:
            raise ValueError("Execution bundle is missing a declared resource.")
    name, description = skill_manifest(files["SKILL.md"])
    if name != snapshot["skill_name"] or description != snapshot["description"]:
        raise ValueError("Execution bundle must match its skill manifest.")
    for stage in stages(snapshot).values():
        if stage["instructions"] not in files or stage["agent_output_schema"] not in files:
            raise ValueError("Execution bundle is missing a declared stage resource.")
    return snapshot


def stages(snapshot):
    """The workflow's named stages, as pinned in its bundle's own workflow.json."""
    import json

    return json.loads(snapshot["files"].get("workflow.json", "{}")).get("stages", {})


def stage_schema(snapshot, stage):
    """The pinned agent output schema of one stage."""
    import json

    return json.loads(snapshot["files"][stages(snapshot)[stage]["agent_output_schema"]])


def build_snapshot(directory, metadata):
    execution = metadata["execution"]
    Draft202012Validator(EXECUTION_SCHEMA).validate(execution)
    names = {
        "workflow.json",
        metadata["instructions"],
        execution["instructions"],
        metadata["tenant_config_schema"],
        metadata["run_config_schema"],
        metadata["output_schema"],
        *execution["resources"],
    }
    if metadata.get("agent_output_schema"):
        names.add(metadata["agent_output_schema"])
    for stage in metadata.get("stages", {}).values():
        names.update((stage["instructions"], stage["agent_output_schema"]))
    files = {name: read_resource(directory, name) for name in sorted(names)}
    # Skills have a fixed entrypoint even when the descriptor uses another filename.
    files["SKILL.md"] = files[metadata["instructions"]]
    skill_name, description = skill_manifest(files["SKILL.md"])
    snapshot = {
        "format_version": 1,
        "key": metadata["key"],
        "definition_version": metadata["version"],
        "skill_name": skill_name,
        "description": description,
        "execution": execution,
        "files": files,
    }
    snapshot["sha256"] = digest(snapshot)
    return validate_snapshot(snapshot)


def build_session_bundle(directory, metadata):
    """The pinned content of a tool-session workflow: model and instruction texts.

    The skill's frontmatter is checked like any skill's and then left out: the
    session is told the procedure, not the manifest.
    """
    sessions = metadata["sessions"]
    Draft202012Validator(SESSIONS_SCHEMA).validate(sessions)
    skill = read_resource(directory, metadata["instructions"])
    skill_manifest(skill)
    stages = {name: read_resource(directory, path) for name, path in sorted(sessions.get("stages", {}).items())}
    if not all(text.strip() for text in stages.values()):
        raise ValueError("Stage instructions must not be empty.")
    return {"format_version": 1, "key": metadata["key"], "definition_version": metadata["version"],
            "model": sessions["model"], "reasoning_effort": sessions.get("reasoning_effort"),
            "instructions": skill.split("---", 2)[2].strip(), "stages": stages, "variant": None}
