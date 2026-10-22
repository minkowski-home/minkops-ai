"""The install command reports a refusal as the operator's next step, never as a traceback."""
import io
import unittest
from unittest.mock import MagicMock, patch

from minkops_api import install_workflows
from minkops_platform.errors import ServiceError


class InstallCommandTests(unittest.TestCase):
    def test_a_refused_workspace_exits_with_its_reason_and_installs_nothing(self):
        refused = ServiceError("conflict", "This workspace exists and belongs to another administrator.")
        with patch('sys.argv', ['install_workflows', 'pr-infra', '--actor-email', 'other@example.test',
                                '--create-tenant', 'PR Infra']), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url'}), \
             patch.object(install_workflows.psycopg, 'connect', MagicMock()), \
             patch.object(install_workflows, 'provision_tenant', side_effect=refused), \
             patch.object(install_workflows, 'install') as install, \
             patch('sys.stderr', new_callable=io.StringIO) as stderr, \
             self.assertRaises(SystemExit) as exited:
            install_workflows.main()
        self.assertEqual(exited.exception.code, 1)
        self.assertEqual(stderr.getvalue(), "This workspace exists and belongs to another administrator.\n")
        install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
