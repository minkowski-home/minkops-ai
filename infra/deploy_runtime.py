"""Deploy the deliberately bounded pilot runtime using versioned images."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

PROJECT = "minkops-ai-prod"
REGION = "us-central1"
INSTANCE = "myndral-prod:us-central1:myndral-db"
JOB = f"projects/{PROJECT}/locations/{REGION}/jobs/minkops-worker"


def run(*args):
    result = subprocess.run(["gcloud", *args, "--quiet"], capture_output=True, text=True)
    if result.returncode:
        # These commands contain only resource names and secret references.
        raise RuntimeError(result.stderr)
    print(f"Ready: {' '.join(args[:4])}", flush=True)


def output(*args):
    return subprocess.run(["gcloud", *args, "--quiet"], check=True, capture_output=True, text=True).stdout.strip()


def private_invoker(service, identity):
    """Keep recovery private even when updating a previously public service.

    Preserve the IAM etag and unrelated bindings; remove only public principals.
    A deployment conflict fails instead of overwriting concurrent IAM edits.
    """
    scope = (f"--project={PROJECT}", f"--region={REGION}")
    policy = json.loads(output("run", "services", "get-iam-policy", service, *scope, "--format=json"))
    public = {"allUsers", "allAuthenticatedUsers"}
    bindings = [{**binding, "members": [member for member in binding.get("members", []) if member not in public]}
                for binding in policy.get("bindings", [])]
    bindings = [binding for binding in bindings if binding["members"]]
    if bindings != policy.get("bindings", []):
        with tempfile.TemporaryDirectory(prefix="minkops-recovery-iam-") as folder:
            path = Path(folder) / "policy.json"
            path.write_text(json.dumps({**policy, "bindings": bindings}))
            run("run", "services", "set-iam-policy", service, str(path), *scope)
    run("run", "services", "add-iam-policy-binding", service, *scope,
        f"--member=serviceAccount:{identity}", "--role=roles/run.invoker")
    verified = json.loads(output("run", "services", "get-iam-policy", service, *scope, "--format=json"))
    if any(public.intersection(binding.get("members", [])) for binding in verified.get("bindings", [])):
        raise RuntimeError("Recovery service still has a public IAM principal; scheduler was not configured.")


def main(image, interest_image):
    scope = (f"--project={PROJECT}", f"--region={REGION}", "--cpu=1")
    common = (*scope, "--memory=512Mi")
    database = "DATABASE_URL=minkops-database-url:1,OPENAI_API_KEY=minkops-openai-key:1"
    run("run", "jobs", "deploy", "minkops-worker", *scope, "--memory=1Gi", f"--image={image}",
        f"--service-account=minkops-worker@{PROJECT}.iam.gserviceaccount.com",
        f"--set-cloudsql-instances={INSTANCE}", "--command=python",
        "--args=-m,minkops_api.accounts_worker,--drain,--lanes,4", "--tasks=1", "--parallelism=1",
        # Leave time for the shared 45-minute budget to stop and reconcile
        # before the infrastructure's hard wall-time cutoff.
        "--max-retries=0", "--task-timeout=3600s", f"--set-secrets={database}",
        f"--set-env-vars=AUTH_DEV_MODE=0,MINKOPS_RUN_TIMEOUT_MINUTES=45,WORKER_JOB_RESOURCE={JOB}")
    for account in ("api", "worker", "ops"):
        run("run", "jobs", "add-iam-policy-binding", "minkops-worker", f"--project={PROJECT}",
            f"--region={REGION}", f"--member=serviceAccount:minkops-{account}@{PROJECT}.iam.gserviceaccount.com",
            "--role=roles/run.invoker")
    sql_number = output("projects", "describe", "myndral-prod", "--format=value(projectNumber)")
    smtp = ",".join(f"SMTP_{key.upper()}=projects/{sql_number}/secrets/myndral-smtp-{key}:latest"
                    for key in ("host", "port", "user", "password"))
    run("run", "deploy", "minkops-solution-api", *scope, "--memory=1Gi", f"--image={image}",
        f"--service-account=minkops-api@{PROJECT}.iam.gserviceaccount.com",
        f"--add-cloudsql-instances={INSTANCE}", "--min=0", "--max=1", "--max-instances=1",
        # Full native discovery is decoded during launch/receipt validation.
        # Bound concurrency while allowing independent companion presence.
        "--concurrency=2", "--timeout=60s", "--no-cpu-boost", "--no-invoker-iam-check",
        f"--set-secrets={database},{smtp}",
        f"--set-env-vars=AUTH_DEV_MODE=0,COOKIE_SECURE=1,MINKOPS_RUN_TIMEOUT_MINUTES=45,PUBLIC_APP_URL=https://app.minkops.com,SMTP_FROM=info@minkops.com,SMTP_EHLO_HOST=minkops.com,SMTP_STARTTLS=1,WORKER_JOB_RESOURCE={JOB}")
    run("run", "deploy", "minkops-interest-api", *common, f"--image={interest_image}",
        f"--service-account=minkops-interest@{PROJECT}.iam.gserviceaccount.com",
        "--min=0", "--max=1", "--max-instances=1", "--concurrency=8", "--timeout=30s",
        "--no-cpu-boost", "--no-invoker-iam-check", f"--set-secrets={smtp}",
        "--set-env-vars=SMTP_FROM_EMAIL=info@minkops.com,SMTP_FROM_NAME=Minkops")
    ops_identity = f"minkops-ops@{PROJECT}.iam.gserviceaccount.com"
    run("run", "deploy", "minkops-operations", f"--project={PROJECT}", f"--region={REGION}",
        "--cpu=1", "--memory=256Mi", f"--image={image}", f"--service-account={ops_identity}",
        f"--set-cloudsql-instances={INSTANCE}", "--command=uvicorn",
        "--args=minkops_api.operations:app,--host,0.0.0.0,--port,8080",
        "--min=0", "--max=1", "--max-instances=1", "--concurrency=1", "--timeout=60s",
        "--no-cpu-boost", "--invoker-iam-check", "--no-allow-unauthenticated",
        "--set-secrets=DATABASE_URL=minkops-database-url:1", f"--set-env-vars=WORKER_JOB_RESOURCE={JOB}")
    private_invoker("minkops-operations", ops_identity)
    operations_url = output("run", "services", "describe", "minkops-operations", f"--project={PROJECT}",
                            f"--region={REGION}", "--format=value(status.url)")
    if not operations_url.startswith("https://") or not operations_url.endswith(".run.app"):
        raise RuntimeError("Recovery service URL is unavailable; scheduler was not configured.")
    jobs = output("scheduler", "jobs", "list", f"--project={PROJECT}", f"--location={REGION}", "--format=value(name)")
    action = "update" if "minkops-worker-recovery" in {name.rsplit("/", 1)[-1] for name in jobs.splitlines()} else "create"
    run("scheduler", "jobs", action, "http", "minkops-worker-recovery", f"--project={PROJECT}",
        f"--location={REGION}", "--schedule=*/5 * * * *", "--time-zone=Etc/UTC",
        f"--uri={operations_url}/reconcile", "--http-method=POST", "--message-body={}",
        f"--oidc-service-account-email={ops_identity}", f"--oidc-token-audience={operations_url}",
        "--max-retry-attempts=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--interest-image", required=True)
    args = parser.parse_args()
    main(args.image, args.interest_image)
