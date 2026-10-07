"""Operator-side Google REST client using the authenticated gcloud account.

Credentials remain in memory. Errors omit response bodies because some control
plane responses can contain secrets. This module is not part of the app image.
"""

import json
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class GoogleApi:
    def __init__(self, project):
        self.project = project
        self.token = subprocess.run(
            ["gcloud", "auth", "print-access-token"], check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def request(self, url, body=None, *, method=None):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".googleapis.com"):
            raise ValueError("Only official Google API endpoints are permitted")
        request = Request(
            url, data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     "x-goog-user-project": self.project,
                     "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=60) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except HTTPError as error:
            raise RuntimeError(f"Google API {error.code}: {parsed.hostname}{parsed.path}") from None

    def wait(self, url, *, timeout=600):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.request(url)
            if result.get("done") or result.get("status") == "DONE":
                if result.get("error"):
                    raise RuntimeError("Google operation failed; inspect its operation ID")
                return result
            time.sleep(3)
        raise TimeoutError(f"Google operation pending: {url}")
