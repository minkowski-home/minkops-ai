"""Release built static sites with gcloud credentials, without a second login.

The checked-in firebase.json remains the serving configuration. Only the selected
build directory is uploaded; symlinks and hidden files are rejected or excluded.
"""

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from google_api import GoogleApi

SITES = {"corporate": "minkops-ai-prod", "console": "minkops-ai-console"}
BASE = "https://firebasehosting.googleapis.com/v1beta1"


def serving_config(configuration):
    headers = [{"glob": rule["source"], "headers": {item["key"]: item["value"] for item in rule["headers"]}}
               for rule in configuration.get("headers", [])]
    rewrites = [{"glob": rule["source"], **({"run": rule["run"]} if "run" in rule else {"path": rule["destination"]})}
                for rule in configuration.get("rewrites", [])]
    return {"headers": headers, "rewrites": rewrites}


def deploy(target, installer=None):
    configuration_path = Path(__file__).with_name("firebase.json")
    configuration = next(item for item in json.loads(configuration_path.read_text())["hosting"] if item["target"] == target)
    directory = (configuration_path.parent / configuration["public"]).resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("Build the frontend before deployment")
    if target == "corporate":
        # Fail closed: never release a download page with a missing/mismatched RC.
        manifest = json.loads((directory.parent / "src/content/windows-release.json").read_text())
        destination = directory / "downloads" / manifest["filename"]
        source = installer or destination
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("Supply the release installer with --installer")
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if source.stat().st_size != manifest["bytes"] or digest != manifest["sha256"]:
            raise RuntimeError("Installer does not match the checked-in release manifest")
        destination.parent.mkdir(exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        destination.with_suffix(".exe.sha256").write_text(f"{manifest['sha256']}  {manifest['filename']}\n")
    files, uploads = {}, {}
    for file in directory.rglob("*"):
        if file.is_symlink():
            raise RuntimeError("Build output must not contain symlinks")
        if not file.is_file() or any(part.startswith(".") for part in file.relative_to(directory).parts):
            continue
        data = gzip.compress(file.read_bytes(), mtime=0)
        digest = hashlib.sha256(data).hexdigest()
        files["/" + file.relative_to(directory).as_posix()] = digest
        uploads[digest] = data
    api = GoogleApi("minkops-ai-prod")
    version = api.request(f"{BASE}/sites/{SITES[target]}/versions", {"config": serving_config(configuration)})
    resource = version["name"]
    for start in range(0, len(files), 1000):
        populated = api.request(f"{BASE}/{resource}:populateFiles", {"files": dict(list(files.items())[start:start+1000])})
        upload_url = populated.get("uploadUrl", "")
        if not upload_url.startswith("https://upload-firebasehosting.googleapis.com/upload/"):
            raise RuntimeError("Unexpected Hosting upload endpoint")
        for digest in populated.get("uploadRequiredHashes", []):
            request = Request(f"{upload_url}/{digest}", data=uploads[digest],
                              headers={"Authorization": f"Bearer {api.token}", "Content-Type": "application/octet-stream"})
            with urlopen(request, timeout=120) as response:
                response.read()
    finalized = api.request(f"{BASE}/{resource}?update_mask=status", {"status": "FINALIZED"}, method="PATCH")
    if finalized["status"] != "FINALIZED":
        raise RuntimeError("Hosting version did not finalize")
    release = api.request(f"{BASE}/sites/{SITES[target]}/releases?" + urlencode({"versionName": resource}), {})
    print(json.dumps({"site": SITES[target], "url": f"https://{SITES[target]}.web.app", "version": resource,
                      "release": release["name"], "file_count": len(files)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=SITES)
    parser.add_argument("--installer", type=Path, help="Corporate release installer matching the manifest")
    args = parser.parse_args()
    deploy(args.target, args.installer)
