"""Invoke a configured Cloud Run job using its runtime service identity.

No downloaded service-account key or caller-supplied URL is accepted. Google
metadata credentials stay outside logs, workflow context and agent bundles.
"""

import json
import os
import re
from urllib.request import Request, urlopen


def run_job():
    job = os.environ["WORKER_JOB_RESOURCE"]
    if not re.fullmatch(r"projects/[a-z0-9-]+/locations/[a-z0-9-]+/jobs/[a-z0-9-]+", job):
        raise ValueError("Invalid worker job resource")
    token_request = Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    with urlopen(token_request, timeout=5) as response:
        token = json.load(response)["access_token"]
    request = Request(
        f"https://run.googleapis.com/v2/{job}:run",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        json.load(response)
