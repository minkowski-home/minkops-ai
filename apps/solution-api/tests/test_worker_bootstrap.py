"""Deployment capacity must reach the shared worker without changing limits."""
import unittest
from unittest.mock import patch

from minkops_api import accounts_worker


class WorkerBootstrapTests(unittest.TestCase):
    def test_bounded_drain_honors_explicit_single_lane(self):
        with patch('sys.argv', ['worker', '--drain', '--lanes', '1']), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url', 'WORKER_JOB_RESOURCE': ''}), \
             patch.object(accounts_worker, 'load_dotenv'), \
             patch('minkops_platform.worker_hosting.drain') as drain:
            accounts_worker.main()
        drain.assert_called_once_with('test-url', lanes=1)

    def test_unbounded_process_uses_the_same_lane_choice(self):
        with patch('sys.argv', ['worker', '--lanes', '2']), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url'}), \
             patch.object(accounts_worker, 'load_dotenv'), \
             patch.object(accounts_worker, 'run_forever') as run:
            accounts_worker.main()
        run.assert_called_once_with('test-url', lanes=2)
