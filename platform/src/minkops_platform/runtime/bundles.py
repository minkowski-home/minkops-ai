"""Repository-owned session bundles, pinned when a run is launched.

A tool-session workflow runs without an execution environment: what it pins
is its model, reasoning effort, service tier and the texts its sessions are
instructed with, nothing that executes. Every text is read from inside the workflow's
own directory; the digest a run stores detects revision drift.
"""

import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

# `stages` names each further kind of session beside the main one, with its own instructions.
SESSIONS_SCHEMA = {
    "type": "object",
    "required": ["model"],
    "additionalProperties": False,
    "properties": {
        "model": {"type": "string", "minLength": 1},
        "reasoning_effort": {"enum": ["low", "medium", "high", "xhigh", "max"]},
        # The provider's tier for the model's requests; `fast` and `priority` keep the model and its effort.
        "service_tier": {"enum": ["default", "priority", "fast"]},
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
        raise ValueError("Workflow files must use relative paths inside the workflow directory.")
    return value


def read_resource(directory: Path, value: str):
    path = directory / relative_path(value)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != directory):
        raise ValueError("Workflow files cannot follow symlinks.")
    if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError("Workflow files must be files inside the workflow directory.")
    if path.stat().st_size > 1_000_000:
        raise ValueError("A workflow file exceeds the supported size.")
    return path.read_text(encoding="utf-8")


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
            "service_tier": sessions.get("service_tier"),
            "instructions": skill.split("---", 2)[2].strip(), "stages": stages, "variant": None}
