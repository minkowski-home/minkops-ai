"""Bound retained deployment artifacts without touching application rows."""

import json
from pathlib import Path
import subprocess

from google_api import GoogleApi

PROJECT = "minkops-ai-prod"


def main():
    subprocess.run(["gcloud", "artifacts", "repositories", "set-cleanup-policies", "minkops",
                    f"--project={PROJECT}", "--location=us-central1",
                    f"--policy={Path(__file__).with_name('artifact-cleanup.json')}", "--no-dry-run", "--quiet"], check=True)
    api = GoogleApi(PROJECT)
    for site in (PROJECT, "minkops-ai-console"):
        url = f"https://firebasehosting.googleapis.com/v1beta1/sites/{site}/channels/live"
        api.request(url + "?updateMask=retainedReleaseCount", {"retainedReleaseCount": 2}, method="PATCH")
        assert api.request(url)["retainedReleaseCount"] == 2
    bucket_url = f"https://logging.googleapis.com/v2/projects/{PROJECT}/locations/global/buckets/_Default"
    bucket = api.request(bucket_url)
    if bucket["retentionDays"] != 30:
        api.request(bucket_url + "?updateMask=retentionDays", {"retentionDays": 30}, method="PATCH")
    print(json.dumps({"artifact_versions_kept": 3, "old_build_days": 30, "hosting_previous_releases": 2,
                      "application_log_days": api.request(bucket_url)["retentionDays"]}))


if __name__ == "__main__":
    main()
