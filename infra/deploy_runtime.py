"""Deploy the deliberately bounded pilot runtime using versioned images."""

import argparse
import subprocess

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


def main(image, interest_image):
    common = (f"--project={PROJECT}", f"--region={REGION}", "--cpu=1", "--memory=512Mi")
    database = "DATABASE_URL=minkops-database-url:1,OPENAI_API_KEY=minkops-openai-key:1"
    run("run", "jobs", "deploy", "minkops-worker", *common, f"--image={image}",
        f"--service-account=minkops-worker@{PROJECT}.iam.gserviceaccount.com",
        f"--set-cloudsql-instances={INSTANCE}", "--command=python",
        "--args=-m,minkops_api.accounts_worker,--drain", "--tasks=1", "--parallelism=1",
        "--max-retries=0", "--task-timeout=1800s", f"--set-secrets={database}",
        f"--set-env-vars=AUTH_DEV_MODE=0,WORKER_JOB_RESOURCE={JOB}")
    for account in ("api", "worker", "ops"):
        run("run", "jobs", "add-iam-policy-binding", "minkops-worker", f"--project={PROJECT}",
            f"--region={REGION}", f"--member=serviceAccount:minkops-{account}@{PROJECT}.iam.gserviceaccount.com",
            "--role=roles/run.invoker")
    sql_number = subprocess.run(["gcloud", "projects", "describe", "myndral-prod",
                                 "--format=value(projectNumber)"], check=True, capture_output=True, text=True).stdout.strip()
    smtp = ",".join(f"SMTP_{key.upper()}=projects/{sql_number}/secrets/myndral-smtp-{key}:latest"
                    for key in ("host", "port", "user", "password"))
    run("run", "deploy", "minkops-solution-api", *common, f"--image={image}",
        f"--service-account=minkops-api@{PROJECT}.iam.gserviceaccount.com",
        f"--add-cloudsql-instances={INSTANCE}", "--min=0", "--max=1", "--max-instances=1",
        # Argon2 account verification consumes memory per request. Two concurrent
        # requests leave headroom in this 512 MiB pilot instead of risking OOMs.
        "--concurrency=2", "--timeout=60s", "--no-cpu-boost", "--no-invoker-iam-check",
        f"--set-secrets={database},{smtp}",
        f"--set-env-vars=AUTH_DEV_MODE=0,COOKIE_SECURE=1,PUBLIC_APP_URL=https://app.minkops.com,SMTP_FROM=info@minkops.com,SMTP_EHLO_HOST=minkops.com,SMTP_STARTTLS=1,WORKER_JOB_RESOURCE={JOB}")
    run("run", "deploy", "minkops-interest-api", *common, f"--image={interest_image}",
        f"--service-account=minkops-interest@{PROJECT}.iam.gserviceaccount.com",
        "--min=0", "--max=1", "--max-instances=1", "--concurrency=8", "--timeout=30s",
        "--no-cpu-boost", "--no-invoker-iam-check", f"--set-secrets={smtp}",
        "--set-env-vars=SMTP_FROM_EMAIL=info@minkops.com,SMTP_FROM_NAME=Minkops")
    jobs = subprocess.run(["gcloud", "scheduler", "jobs", "list", f"--project={PROJECT}",
                           f"--location={REGION}", "--format=value(name)"], check=True, capture_output=True, text=True).stdout
    action = "update" if "minkops-worker-recovery" in jobs else "create"
    run("scheduler", "jobs", action, "http", "minkops-worker-recovery", f"--project={PROJECT}",
        f"--location={REGION}", "--schedule=0 * * * *", "--time-zone=Etc/UTC",
        f"--uri=https://run.googleapis.com/v2/{JOB}:run", "--http-method=POST", "--message-body={}",
        f"--oauth-service-account-email=minkops-ops@{PROJECT}.iam.gserviceaccount.com",
        "--oauth-token-scope=https://www.googleapis.com/auth/cloud-platform", "--max-retry-attempts=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--interest-image", required=True)
    args = parser.parse_args()
    main(args.image, args.interest_image)
