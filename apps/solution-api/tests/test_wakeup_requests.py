"""Polling a companion cannot allocate worker-dispatch database connections."""
import pytest

from minkops_api.main import wakes_worker


@pytest.mark.parametrize('path', [
    '/api/desktop/worker/claim', '/api/desktop/worker/heartbeat',
    '/api/desktop/worker/jobs/job/progress', '/api/auth/login', '/api/auth/logout',
    '/api/tenants/client/attention/refresh',
])
def test_polling_and_account_maintenance_do_not_dispatch(path):
    assert not wakes_worker('POST', path, 200)


@pytest.mark.parametrize('path', [
    '/api/tenants/client/accounts/runs', '/api/desktop/worker/jobs/job/finish',
    '/api/tenants/client/attention/item/profile',
    '/api/tenants/client/attention/bills/run/file',
    '/api/tenants/client/tasks/task/control',
])
def test_committed_work_transitions_dispatch(path):
    assert wakes_worker('POST', path, 202)
    assert not wakes_worker('GET', path, 200)
    assert not wakes_worker('POST', path, 409)
