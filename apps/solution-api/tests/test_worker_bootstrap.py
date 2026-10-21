"""Deployment capacity must reach the shared worker without changing limits."""
import unittest
from unittest.mock import patch

from minkops_api import accounts_worker


class WorkerBootstrapTests(unittest.TestCase):
    def test_bounded_drain_honors_explicit_lanes_and_serves_run_items_beside_it(self):
        with patch('sys.argv', ['worker', '--drain', '--lanes', '1', '--desk-lanes', '3']), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url', 'WORKER_JOB_RESOURCE': ''}), \
             patch.object(accounts_worker, 'load_dotenv'), \
             patch.object(accounts_worker, 'Host') as host, \
             patch('minkops_platform.worker_hosting.drain') as drain:
            accounts_worker.main()
        host.assert_called_once_with('test-url', lanes=3)
        drain.assert_called_once_with('test-url', lanes=1, host=host.return_value.__enter__.return_value)

    def test_unbounded_process_uses_the_same_lane_choices(self):
        with patch('sys.argv', ['worker', '--lanes', '2']), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url'}), \
             patch.object(accounts_worker, 'load_dotenv'), \
             patch.object(accounts_worker, 'Host') as host, \
             patch.object(accounts_worker, 'run_forever') as run:
            accounts_worker.main()
        host.assert_called_once_with('test-url', lanes=accounts_worker.DESK_LANES)
        run.assert_called_once_with('test-url', lanes=2)
