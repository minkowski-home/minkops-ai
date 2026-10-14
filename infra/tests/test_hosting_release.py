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


def release_tree(tmp_path, monkeypatch, payload=b"reviewed installer"):
    """A corporate build with a manifest-matching installer and its update feed."""
    import base64

    build = tmp_path / "site/dist"
    build.mkdir(parents=True)
    (build / "index.html").write_text("release page")
    content = tmp_path / "site/src/content"
    content.mkdir(parents=True)
    manifest = {"version": "0.7.0", "filename": "Minkops-Setup-0.7.0.exe", "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}
    (content / "windows-release.json").write_text(json.dumps(manifest))
    (tmp_path / "firebase.json").write_text(json.dumps({"hosting": [{"target": "corporate", "public": "site/dist"}]}))
    monkeypatch.setattr(hosting, "__file__", str(tmp_path / "deploy_hosting.py"))
    installer = tmp_path / "release/Minkops-Setup-0.7.0.exe"
    installer.parent.mkdir()
    installer.write_bytes(payload)
    sha512 = base64.b64encode(hashlib.sha512(payload).digest()).decode()
    feed = tmp_path / "release/latest.yml"
    feed.write_text(f"version: 0.7.0\nfiles:\n  - url: Minkops-Setup-0.7.0.exe\n    sha512: {sha512}\n"
                    f"    size: {len(payload)}\npath: Minkops-Setup-0.7.0.exe\nsha512: {sha512}\n"
                    "releaseDate: '2026-10-14T00:00:00.000Z'\n")
    (tmp_path / "release/Minkops-Setup-0.7.0.exe.blockmap").write_bytes(b"blockmap")
    return build, installer, feed


@pytest.mark.parametrize("problem", ["missing", "version", "path", "sha512"])
def test_an_update_feed_must_describe_exactly_the_released_installer(tmp_path, monkeypatch, problem):
    build, installer, feed = release_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(hosting, "GoogleApi", lambda *args: pytest.fail("Invalid feeds never reach the cloud"))
    if problem == "missing":
        feed.unlink()
    else:
        text = feed.read_text()
        feed.write_text({"version": text.replace("version: 0.7.0", "version: 0.7.1"),
                         "path": text.replace("path: Minkops", "path: Other"),
                         "sha512": text.replace("\nsha512: ", "\nsha512: AAAA")}[problem])
    with pytest.raises(RuntimeError, match="update feed"):
        hosting.deploy("corporate", installer)
    assert not (build / "downloads").exists()


def test_a_valid_feed_is_published_next_to_the_installer(tmp_path, monkeypatch):
    build, installer, feed = release_tree(tmp_path, monkeypatch)

    class Stop(Exception):
        pass

    def stop(*args):
        raise Stop()

    monkeypatch.setattr(hosting, "GoogleApi", stop)
    with pytest.raises(Stop):
        hosting.deploy("corporate", installer)
    downloads = build / "downloads"
    assert (downloads / "Minkops-Setup-0.7.0.exe").read_bytes() == installer.read_bytes()
    assert (downloads / "latest.yml").read_text() == feed.read_text()
    assert (downloads / "Minkops-Setup-0.7.0.exe.blockmap").read_bytes() == b"blockmap"
