"""Reapplying the cost envelope updates existing scoped budgets in place."""
import importlib.util
import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
spec = importlib.util.spec_from_file_location('billing_setup', INFRA / 'bootstrap_hosting.py')
billing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(billing)


def test_existing_minkops_budgets_are_updated_without_touching_other_projects(monkeypatch):
    original = [
        {'name': 'billingAccounts/test/budgets/one', 'displayName': 'Minkops hosting monthly target CAD 15', 'etag': 'first'},
        {'name': 'billingAccounts/test/budgets/two', 'displayName': 'Minkops Cloud Run spend cap CAD 10', 'etag': 'second'},
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
    assert len(calls) == 2
    assert all(method == 'PATCH' for _, _, method in calls)
    assert [body['amount']['specifiedAmount']['units'] for _, body, _ in calls] == ['10', '6']
    assert calls[1][1]['spendCap'] == {'inputState': 'CONFIGURED'}
    assert 'spendCap.inputState' in calls[1][0]
    assert calls[1][1]['budgetFilter']['services'] == ['services/152E-C115-5142']
    assert calls[0][1]['etag'] == 'first'
    assert all(body['budgetFilter']['projects'] == ['projects/minkops-ai-prod'] for _, body, _ in calls)
