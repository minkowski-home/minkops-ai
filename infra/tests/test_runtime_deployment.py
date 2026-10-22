"""Recovery polls private eligibility; idle scheduler ticks cannot launch jobs."""
import base64
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from psycopg.conninfo import conninfo_to_dict

from infra import deploy_runtime


def deployment(monkeypatch, scheduled=""):
    """The commands a deployment runs, when `scheduled` names the scheduler jobs that exist."""
    commands = []
    monkeypatch.setattr(deploy_runtime, "run", lambda *args: commands.append(args))
    monkeypatch.setattr(deploy_runtime, "private_invoker", lambda *args: commands.append(("private_invoker", *args)))

    def output(*args):
        if args[:2] == ("projects", "describe"):
            return "123456"
        if args[:4] == ("run", "services", "describe", "minkops-operations"):
            return "https://minkops-operations-test.run.app"
        return scheduled

    monkeypatch.setattr(deploy_runtime, "output", output)
    deploy_runtime.main("runtime-image", "interest-image")
    return commands


@pytest.mark.parametrize("existing,action", [("", "create"), ("minkops-worker-recovery", "update")])
def test_deployment_uses_a_private_bounded_recovery_service_and_oidc_scheduler(monkeypatch, existing, action):
    commands = deployment(monkeypatch, existing)
    ops = next(c for c in commands if c[:3] == ("run", "deploy", "minkops-operations"))
    for flag in ("--min=0", "--max=1", "--max-instances=1", "--cpu=1", "--memory=256Mi",
                 "--concurrency=1", "--invoker-iam-check", "--no-allow-unauthenticated"):
        assert flag in ops
    assert "--no-invoker-iam-check" not in ops
    assert "--set-secrets=DATABASE_URL=minkops-books-database-url:1" in ops
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


class SecretManager:
    """Secret Manager holding these secrets, each with the version it was created with."""

    def __init__(self, *existing):
        self.versions = {name: ["(as created)"] for name in existing}

    def request(self, url, body=None):
        last = url.rsplit("/", 1)[-1]
        if body is None:
            return {"secrets": [{"name": f"projects/minkops-ai-prod/secrets/{name}"} for name in self.versions]}
        if "?secretId=" in last:
            self.versions[last.split("=", 1)[1]] = []
        else:
            self.versions[last.removesuffix(":addVersion")].append(base64.b64decode(body["payload"]["data"]).decode())
        return {}


def test_configuration_writes_the_rebuilds_own_secrets_and_leaves_the_parked_builds(monkeypatch, tmp_path):
    """Production holds the parked build's database secrets, naming the shared instance, and the model key.
    Configuration writes the rebuild's beside them, for the instance its deployment mounts, and leaves the
    parked build's as they are for a rollback; every secret the deployment reads then exists."""
    monkeypatch.syspath_prepend(str(Path(deploy_runtime.__file__).parent))
    import configure_runtime

    manager = SecretManager("minkops-database-url", "minkops-migration-url", "minkops-openai-key")
    commands = []
    monkeypatch.setattr(configure_runtime, "GoogleApi", lambda project: manager)
    monkeypatch.setattr(configure_runtime, "ensure_service_accounts", Mock())
    monkeypatch.setattr(configure_runtime, "command", lambda *args: commands.append(args))
    monkeypatch.setattr(configure_runtime, "dotenv_values", lambda _: {"OPENAI_API_KEY": "test-key"})
    (tmp_path / "database.json").write_text(json.dumps({"runtime_password": "runtime-pw", "migration_password": "migrate-pw"}))
    configure_runtime.main(tmp_path)

    assert manager.versions["minkops-database-url"] == manager.versions["minkops-migration-url"] == ["(as created)"]
    (runtime,), (migration,) = manager.versions["minkops-books-database-url"], manager.versions["minkops-books-migration-url"]
    runtime, migration = conninfo_to_dict(runtime), conninfo_to_dict(migration)
    assert runtime["host"] == migration["host"] == "/cloudsql/minkops-ai-prod:us-central1:minkops-books"
    assert (runtime["user"], runtime["password"]) == ("minkops_app", "runtime-pw") and not runtime.get("options")
    assert (migration["user"], migration["password"], migration["options"]) == ("minkops_migrate", "migrate-pw",
                                                                                "-c role=minkops_owner")

    granted = {}
    for target, role, member in ((c[2], c[-1], c[-2]) for c in commands):
        granted.setdefault((target, role.removeprefix("--role=")), set()).add(member.split("minkops-", 1)[1].split("@")[0])
    assert granted[("minkops-ai-prod", "roles/cloudsql.client")] == {"api", "worker", "ops"}
    assert not any(target == "myndral-prod" for target, _ in granted)
    reads = {secret: who for (secret, role), who in granted.items() if role == "roles/secretmanager.secretAccessor"}
    assert reads["minkops-books-database-url"] == {"api", "worker", "ops"}
    assert reads["minkops-books-migration-url"] == {"ops"}
    assert reads["minkops-openai-key"] == {"api", "worker"}

    deployed = deployment(monkeypatch)
    mounted = {arg.split("=", 1)[1] for c in deployed for arg in c
               if arg.startswith(("--set-cloudsql-instances=", "--add-cloudsql-instances="))}
    assert mounted == {"minkops-ai-prod:us-central1:minkops-books"}
    read = {pair.split("=", 1)[1].rsplit(":", 1)[0] for c in deployed for arg in c if arg.startswith("--set-secrets=")
            for pair in arg.removeprefix("--set-secrets=").split(",")}
    assert {"minkops-books-database-url", "minkops-openai-key"} <= {name for name in read if "/" not in name} <= set(manager.versions)
