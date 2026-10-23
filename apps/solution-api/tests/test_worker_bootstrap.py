"""The worker command hosts its lanes for good, or drains them to idle for scale-to-zero hosting."""
import unittest
from unittest.mock import patch

from minkops_api import accounts_worker


class WorkerBootstrapTests(unittest.TestCase):
    def run_worker(self, *arguments):
        with patch('sys.argv', ['worker', *arguments]), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url', 'WORKER_JOB_RESOURCE': ''}), \
             patch.object(accounts_worker, 'load_dotenv'), \
             patch.object(accounts_worker, 'Host') as host, \
             patch.object(accounts_worker, 'drain') as drain, \
             patch.object(accounts_worker, 'serve') as serve:
            accounts_worker.main()
        return host, drain, serve

    def test_a_bounded_drain_serves_the_chosen_lanes_until_idle(self):
        host, drain, serve = self.run_worker('--drain', '--lanes', '3')
        host.assert_called_once_with('test-url', lanes=3)
        drain.assert_called_once_with('test-url', host.return_value.__enter__.return_value)
        serve.assert_not_called()

    def test_a_hosted_worker_serves_the_default_lanes_until_it_is_stopped(self):
        host, drain, serve = self.run_worker()
        host.assert_called_once_with('test-url', lanes=accounts_worker.LANES)
        serve.assert_called_once_with('test-url')
        drain.assert_not_called()

    def test_lanes_outside_what_a_worker_supports_are_refused(self):
        for lanes in ('0', '17'):
            with self.subTest(lanes=lanes), self.assertRaises(SystemExit):
                self.run_worker('--lanes', lanes)
