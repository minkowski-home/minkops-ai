"""Install scoped runtime identities/secrets without displaying secret payloads.

The runtime's database secrets are named for the instance they open
(minkops-books-database-url, minkops-books-migration-url). A secret that exists is
never rewritten, so a new database always gets new secrets.
"""

import argparse
import base64
import json
import subprocess
from pathlib import Path

from deploy_runtime import INSTANCE, PROJECT
from dotenv import dotenv_values
from google_api import GoogleApi
from psycopg.conninfo import make_conninfo

# The mail credentials both products send with.
SMTP_PROJECT = "myndral-prod"


def command(*arguments):
    subprocess.run(["gcloud", *arguments, "--quiet"], check=True, capture_output=True)


def secret(api, name, value, identities):
    base = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets"
    existing = api.request(base).get("secrets", [])
    if not any(item["name"].endswith("/" + name) for item in existing):
        api.request(f"{base}?secretId={name}", {"replication": {"automatic": {}}})
        api.request(f"{base}/{name}:addVersion", {"payload": {"data": base64.b64encode(value.encode()).decode()}})
    for identity in identities:
        command("secrets", "add-iam-policy-binding", name, f"--project={PROJECT}",
                f"--member=serviceAccount:{identity}", "--role=roles/secretmanager.secretAccessor")
    print(f"Scoped secret ready: {name}")


def ensure_service_accounts(api, identities):
    base = f"https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts"
    accounts = api.request(base).get("accounts", [])
    existing = {item["email"] for item in accounts}
    for name, email in identities.items():
        if email not in existing:
            api.request(base, {"accountId": f"minkops-{name}",
                               "serviceAccount": {"displayName": f"Minkops {name}"}})


def main(state_dir):
    api = GoogleApi(PROJECT)
    identities = {name: f"minkops-{name}@{PROJECT}.iam.gserviceaccount.com"
                  for name in ("api", "worker", "ops", "interest")}
    ensure_service_accounts(api, identities)
    for name in ("api", "worker", "ops"):
        command("projects", "add-iam-policy-binding", PROJECT,
                f"--member=serviceAccount:{identities[name]}", "--role=roles/cloudsql.client")
    # The credentials provision_database.py created on that instance.
    state = json.loads((state_dir / "database.json").read_text())
    for name, user, password, recipients, options in (
        ("minkops-books-database-url", "minkops_app", state["runtime_password"], [identities["api"], identities["worker"], identities["ops"]], ""),
        ("minkops-books-migration-url", "minkops_migrate", state["migration_password"], [identities["ops"]], "-c role=minkops_owner"),
    ):
        value = make_conninfo(host=f"/cloudsql/{INSTANCE}", dbname="minkops", user=user,
                             password=password, connect_timeout=10, options=options)
        secret(api, name, value, recipients)
    key = dotenv_values(Path(__file__).resolve().parents[1] / "apps/solution-api/.env").get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Confirmed local OpenAI key is unavailable")
    secret(api, "minkops-openai-key", key, [identities["worker"], identities["api"]])
    for name in ("host", "port", "user", "password"):
        for identity in (identities["api"], identities["interest"]):
            command("secrets", "add-iam-policy-binding", f"myndral-smtp-{name}", f"--project={SMTP_PROJECT}",
                    f"--member=serviceAccount:{identity}", "--role=roles/secretmanager.secretAccessor")
    print("Cloud SQL client roles and per-secret SMTP access configured; no service-account keys created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True, help="The state provision_database.py wrote.")
    main(parser.parse_args().state_dir)
