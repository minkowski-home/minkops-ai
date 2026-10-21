"""Only committed changes that can make run items runnable dispatch the worker; polling never does."""
import pytest

from minkops_api.main import wakes_worker


@pytest.mark.parametrize('path', [
    '/api/desktop/worker/claim', '/api/desktop/worker/heartbeat', '/api/desktop/worker/jobs/job/sync',
    '/api/auth/login', '/api/auth/logout', '/api/tenants/t/accounts/sources', '/api/tenants/t/attention/item/done',
])
def test_polling_and_account_maintenance_do_not_dispatch(path):
    assert not wakes_worker('POST', path, 200)


@pytest.mark.parametrize('path', [
    '/api/tenants/t/clients/c/runs', '/api/tenants/t/clients/c/runs/run/approve',
    '/api/tenants/t/clients/c/records/record/decisions', '/api/tenants/t/clients/c/companies/company/authorise',
    '/api/desktop/worker/jobs/job/finish', '/api/tenants/t/attention/item/decision', '/api/tenants/t/tasks/task/control',
])
def test_committed_work_transitions_dispatch(path):
    assert wakes_worker('POST', path, 202)
    assert not wakes_worker('GET', path, 200)
    assert not wakes_worker('POST', path, 409)
