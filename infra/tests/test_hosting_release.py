"""Publication must reject a bad installer before making any cloud mutation."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
spec = importlib.util.spec_from_file_location("hosting_release", INFRA / "deploy_hosting.py")
hosting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosting)


@pytest.mark.parametrize("problem", ["missing", "size", "digest", "symlink"])
def test_invalid_installer_cannot_create_a_hosting_version(tmp_path, monkeypatch, problem):
    build = tmp_path / "site/dist"
    build.mkdir(parents=True)
    (build / "index.html").write_text("release page")
    content = tmp_path / "site/src/content"
    content.mkdir(parents=True)
    payload = b"reviewed installer"
    manifest = {"filename": "setup.exe", "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}
    (content / "windows-release.json").write_text(json.dumps(manifest))
    (tmp_path / "firebase.json").write_text(json.dumps({"hosting": [
        {"target": "corporate", "public": "site/dist"}]}))
    monkeypatch.setattr(hosting, "__file__", str(tmp_path / "deploy_hosting.py"))

    def forbidden_api(*args):
        pytest.fail("Invalid artifacts must never reach the cloud client")

    monkeypatch.setattr(hosting, "GoogleApi", forbidden_api)
    installer = tmp_path / "installer.exe"
    if problem == "size":
        installer.write_bytes(b"short")
    elif problem == "digest":
        installer.write_bytes(b"x" * len(payload))
    elif problem == "symlink":
        target = tmp_path / "actual.exe"
        target.write_bytes(payload)
        installer.symlink_to(target)
    with pytest.raises(RuntimeError, match="installer|Installer"):
        hosting.deploy("corporate", installer)
    assert not (build / "downloads").exists()
