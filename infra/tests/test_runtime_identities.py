"""A fresh project must get every referenced identity before IAM deployment."""

import importlib.util
from pathlib import Path
import sys

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
spec = importlib.util.spec_from_file_location("runtime_setup", INFRA / "configure_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_missing_runtime_identities_are_created_and_existing_accounts_are_preserved():
    identities = {name: f"minkops-{name}@minkops-ai-prod.iam.gserviceaccount.com"
                  for name in ("api", "worker", "ops", "interest")}

    class ProjectApi:
        def __init__(self):
            self.accounts = {identities["api"]}
            self.created = []

        def request(self, url, body=None):
            assert url == "https://iam.googleapis.com/v1/projects/minkops-ai-prod/serviceAccounts"
            if body is None:
                return {"accounts": [{"email": email} for email in self.accounts]}
            email = body["accountId"] + "@minkops-ai-prod.iam.gserviceaccount.com"
            assert email not in self.accounts
            self.accounts.add(email)
            self.created.append(body["accountId"])
            return {"email": email}

    api = ProjectApi()
    runtime.ensure_service_accounts(api, identities)
    assert api.accounts == set(identities.values())
    assert set(api.created) == {"minkops-worker", "minkops-ops", "minkops-interest"}
    runtime.ensure_service_accounts(api, identities)
    assert len(api.created) == 3
