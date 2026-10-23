"""Reapplying the cost envelope updates existing scoped budgets in place."""
import importlib.util
import sys
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
spec = importlib.util.spec_from_file_location('billing_setup', INFRA / 'bootstrap_hosting.py')
billing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(billing)


# The project target as billing holds it before the dedicated instance's envelope, and after it is applied once.
@pytest.mark.parametrize('project_target', ['Minkops exclusive resources target CAD 10', 'Minkops project target CAD 25'])
def test_existing_minkops_budgets_are_updated_without_touching_other_projects(monkeypatch, project_target):
    original = [
        {'name': 'billingAccounts/test/budgets/one', 'displayName': project_target, 'etag': 'first'},
        {'name': 'billingAccounts/test/budgets/two', 'displayName': 'Minkops Cloud Run spend cap CAD 6', 'etag': 'second'},
        {'name': 'billingAccounts/test/budgets/other', 'displayName': 'Other project'},
    ]
    calls = []

    class Api:
        def request(self, url, body=None, *, method=None):
            if body is None:
                return {'budgets': original}
            calls.append((url, body, method))
            return body

    monkeypatch.setattr(billing, 'GoogleApi', lambda _: Api())
    billing.budgets()
    assert [url.split('?')[0].rsplit('/', 1)[1] for url, _, _ in calls] == ['one', 'two']
    assert all(method == 'PATCH' for _, _, method in calls)
    assert [body['amount']['specifiedAmount']['units'] for _, body, _ in calls] == ['25', '6']
    # The project target counts every service, so minkops-books' CAD 15 sits inside it.
    assert calls[0][1]['displayName'] == 'Minkops project target CAD 25'
    assert 'services' not in calls[0][1]['budgetFilter']
    assert calls[1][1]['spendCap'] == {'inputState': 'CONFIGURED'}
    assert 'spendCap.inputState' in calls[1][0]
    assert calls[1][1]['budgetFilter']['services'] == ['services/152E-C115-5142']
    assert calls[0][1]['etag'] == 'first'
    assert all(body['budgetFilter']['projects'] == ['projects/minkops-ai-prod'] for _, body, _ in calls)
