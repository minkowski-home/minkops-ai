"""Job routing is deployment-owned; metadata credentials stay in memory."""

import io
import os
import unittest
from unittest.mock import patch

from minkops_connectors.cloud_run import run_job


class CloudRunTests(unittest.TestCase):
    def test_invalid_resource_never_contacts_metadata_or_network(self):
        with patch.dict(os.environ, {"WORKER_JOB_RESOURCE": "https://attacker.example"}), patch(
            "minkops_connectors.cloud_run.urlopen"
        ) as network:
            with self.assertRaises(ValueError):
                run_job()
            network.assert_not_called()

    def test_fixed_metadata_and_job_endpoints_with_ephemeral_token(self):
        calls = []

        def response(request, **kwargs):
            calls.append(request)
            return io.BytesIO(b'{"access_token":"ephemeral"}' if len(calls) == 1 else b'{}')

        with patch.dict(os.environ, {"WORKER_JOB_RESOURCE": "projects/test/locations/us-central1/jobs/worker"}), patch(
            "minkops_connectors.cloud_run.urlopen", side_effect=response
        ):
            run_job()
        self.assertEqual(calls[0].get_header("Metadata-flavor"), "Google")
        self.assertEqual(calls[1].full_url, "https://run.googleapis.com/v2/projects/test/locations/us-central1/jobs/worker:run")
        self.assertEqual(calls[1].get_header("Authorization"), "Bearer ephemeral")
        self.assertEqual(calls[1].data, b"{}")
