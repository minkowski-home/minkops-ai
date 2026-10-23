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


    def test_a_new_workspace_prints_its_first_admins_sign_up_link_once(self):
        from datetime import datetime
        with patch('sys.argv', ['install_workflows', 'pr-infra', '--actor-email', 'owner@client.example',
                                '--create-tenant', 'PR Infra']), \
             patch.dict('os.environ', {'DATABASE_URL': 'test-url', 'PUBLIC_APP_URL': 'https://app.example'}), \
             patch.object(install_workflows.psycopg, 'connect', MagicMock()), \
             patch.object(install_workflows, 'provision_tenant', return_value=('tenant', 'token-1')), \
             patch.object(install_workflows, 'invitation_expiry', return_value=datetime(2026, 10, 30)), \
             patch.object(install_workflows, 'install', return_value=['bill-entry']) as install, \
             patch('sys.stdout', new_callable=io.StringIO) as stdout:
            install_workflows.main()
        install.assert_called_once()
        self.assertEqual(install.call_args.kwargs, {"actor_email": None})
        self.assertEqual(stdout.getvalue(), (
            "Installed: bill-entry.\n"
            "Send owner@client.example this sign-up link to join PR Infra as its admin. It works once, until "
            "30 October 2026:\nhttps://app.example/invite/token-1\n"))

if __name__ == '__main__':
    unittest.main()
