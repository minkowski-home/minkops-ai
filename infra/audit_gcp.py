"""Read-only project inventory. Never enables APIs or reads secret payloads.

Run with authenticated gcloud and redirect JSON to an untracked local file.
Only selected service settings are emitted; environment values are omitted.
"""

import argparse
import json
import subprocess


def audit(gcloud):
    def read(*args):
        result = subprocess.run(
            [gcloud, *args, "--quiet", "--format=json"], capture_output=True, text=True, timeout=60
        )
        if result.returncode:
            return {
                "unavailable": result.stderr.splitlines()[0] if result.stderr else "Request failed"
            }
        return json.loads(result.stdout or "null")

    projects = read("projects", "list")
    inventory = {"billing_accounts": read("billing", "accounts", "list"), "projects": []}
    if not isinstance(projects, list):
        raise RuntimeError("Cannot list projects")
    for project in projects:
        project_id = project["projectId"]
        resources = {
            "project": project_id,
            "billing": read("billing", "projects", "describe", project_id),
        }
        services = read("services", "list", "--enabled", f"--project={project_id}")
        enabled = {s["config"]["name"] for s in services} if isinstance(services, list) else set()
        resources["enabled_apis"] = sorted(enabled)
        for api, key, command in [
            ("run.googleapis.com", "run_services", ("run", "services", "list")),
            ("sqladmin.googleapis.com", "sql", ("sql", "instances", "list")),
            ("compute.googleapis.com", "vms", ("compute", "instances", "list")),
            (
                "artifactregistry.googleapis.com",
                "artifact_repositories",
                ("artifacts", "repositories", "list", "--location=all"),
            ),
            ("secretmanager.googleapis.com", "secret_names", ("secrets", "list")),
            ("storage.googleapis.com", "buckets", ("storage", "buckets", "list")),
        ]:
            if api not in enabled:
                resources[key] = {"api_enabled": False}
                continue
            values = read(*command, f"--project={project_id}")
            if not isinstance(values, list):
                resources[key] = values
                continue
            if key == "run_services":
                resources[key] = [
                    {
                        "name": s["metadata"]["name"],
                        "region": s["metadata"]
                        .get("labels", {})
                        .get("cloud.googleapis.com/location"),
                        "url": s.get("status", {}).get("url"),
                        "service_annotations": s["metadata"].get("annotations", {}),
                        "instance_annotations": s["spec"]["template"]["metadata"].get(
                            "annotations", {}
                        ),
                        "resources": [
                            c.get("resources", {})
                            for c in s["spec"]["template"]["spec"]["containers"]
                        ],
                        "service_account": s["spec"]["template"]["spec"].get("serviceAccountName"),
                        "secret_names": [
                            e["valueFrom"]["secretKeyRef"]["name"]
                            for c in s["spec"]["template"]["spec"]["containers"]
                            for e in c.get("env", [])
                            if "secretKeyRef" in e.get("valueFrom", {})
                        ],
                    }
                    for s in values
                ]
            elif key == "sql":
                resources[key] = [
                    {
                        k: s.get(k)
                        for k in ("name", "region", "databaseVersion", "state", "settings")
                    }
                    for s in values
                ]
            elif key == "vms":
                resources[key] = [
                    {k: s.get(k) for k in ("name", "zone", "machineType", "status")} for s in values
                ]
            else:
                resources[key] = [
                    {k: s.get(k) for k in ("name", "location", "storageClass", "format")}
                    for s in values
                ]
        inventory["projects"].append(resources)
    return inventory


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcloud", default="gcloud")
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.gcloud), indent=2))
