"""Recovery polls private eligibility; idle scheduler ticks cannot launch jobs."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from infra import deploy_runtime


@pytest.mark.parametrize("existing,action", [("", "create"), ("minkops-worker-recovery", "update")])
def test_deployment_uses_a_private_bounded_recovery_service_and_oidc_scheduler(monkeypatch, existing, action):
    commands = []
    monkeypatch.setattr(deploy_runtime, "run", lambda *args: commands.append(args))
    monkeypatch.setattr(deploy_runtime, "private_invoker", lambda *args: commands.append(("private_invoker", *args)))

    def output(*args):
        if args[:2] == ("projects", "describe"):
            return "123456"
        if args[:4] == ("run", "services", "describe", "minkops-operations"):
            return "https://minkops-operations-test.run.app"
        return existing

    monkeypatch.setattr(deploy_runtime, "output", output)
    deploy_runtime.main("runtime-image", "interest-image")
    ops = next(c for c in commands if c[:3] == ("run", "deploy", "minkops-operations"))
    for flag in ("--min=0", "--max=1", "--max-instances=1", "--cpu=1", "--memory=256Mi",
                 "--concurrency=1", "--invoker-iam-check", "--no-allow-unauthenticated"):
        assert flag in ops
    assert "--no-invoker-iam-check" not in ops
    assert "--set-secrets=DATABASE_URL=minkops-database-url:1" in ops
    assert not any("OPENAI_API_KEY" in arg for arg in ops)
    scheduler = next(c for c in commands if c[:2] == ("scheduler", "jobs"))
    assert scheduler[2] == action
    assert "--schedule=*/5 * * * *" in scheduler
    assert "--uri=https://minkops-operations-test.run.app/reconcile" in scheduler
    assert "--oidc-token-audience=https://minkops-operations-test.run.app" in scheduler
    assert any(a.startswith("--oidc-service-account-email=minkops-ops@") for a in scheduler)
    assert not any("oauth" in a or "run.googleapis.com" in a for a in scheduler)
    worker = next(c for c in commands if c[:4] == ("run", "jobs", "deploy", "minkops-worker"))
    assert "--args=-m,minkops_api.accounts_worker,--drain,--lanes,12" in worker
    assert "--memory=1Gi" in worker and "--memory=512Mi" not in worker
    api = next(c for c in commands if c[:3] == ("run", "deploy", "minkops-solution-api"))
    assert "--memory=1Gi" in api and "--concurrency=2" in api


def test_private_invoker_removes_public_members_without_losing_other_policy(monkeypatch):
    original = {"version": 3, "etag": "preserve-concurrency-fence", "bindings": [
        {"role": "roles/run.invoker", "members": ["allUsers", "allAuthenticatedUsers", "user:operator@example.test"]},
        {"role": "roles/run.admin", "members": ["user:operator@example.test"]}]}
    clean = {**original, "bindings": [
        {"role": "roles/run.invoker", "members": ["user:operator@example.test"]}, original["bindings"][1]]}
    monkeypatch.setattr(deploy_runtime, "output", Mock(side_effect=[json.dumps(original), json.dumps(clean)]))
    writes, commands = [], []

    def run(*args):
        commands.append(args)
        if args[:3] == ("run", "services", "set-iam-policy"):
            writes.append(json.loads(Path(args[4]).read_text()))

    monkeypatch.setattr(deploy_runtime, "run", run)
    deploy_runtime.private_invoker("minkops-operations", "scheduler@example.test")
    assert writes == [clean]
    assert any("--member=serviceAccount:scheduler@example.test" in command and "--role=roles/run.invoker" in command
               for command in commands)


def test_private_policy_verification_fails_closed(monkeypatch):
    public = json.dumps({"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]})
    monkeypatch.setattr(deploy_runtime, "output", Mock(return_value=public))
    monkeypatch.setattr(deploy_runtime, "run", Mock())
    with pytest.raises(RuntimeError, match="still has a public IAM principal"):
        deploy_runtime.private_invoker("minkops-operations", "scheduler@example.test")


def test_runtime_database_secret_is_granted_to_operations_not_ai_key(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(deploy_runtime.__file__).parent))
    import configure_runtime

    monkeypatch.setattr(configure_runtime, "GoogleApi", Mock())
    monkeypatch.setattr(configure_runtime, "ensure_service_accounts", Mock())
    monkeypatch.setattr(configure_runtime, "command", Mock())
    monkeypatch.setattr(configure_runtime, "dotenv_values", lambda _: {"OPENAI_API_KEY": "test-key"})
    monkeypatch.setattr(Path, "read_text", lambda _: json.dumps({"runtime_password": "test", "migration_password": "test"}))
    grant = Mock()
    monkeypatch.setattr(configure_runtime, "secret", grant)
    configure_runtime.main()
    calls = {call.args[1]: call.args for call in grant.call_args_list}
    ops = f"minkops-ops@{deploy_runtime.PROJECT}.iam.gserviceaccount.com"
    assert ops in calls["minkops-database-url"][3]
    assert "user=minkops_app" in calls["minkops-database-url"][2]
    assert "role=minkops_owner" not in calls["minkops-database-url"][2]
    assert ops not in calls["minkops-openai-key"][3]
