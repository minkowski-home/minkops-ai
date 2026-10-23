"""The dedicated instance is created once, isolated and recoverable, never altered."""
import pytest

from infra import provision_database


class Api:
    def __init__(self, existing=None):
        self.existing, self.calls = existing, []

    def request(self, url, body=None, *, method=None):
        self.calls.append((url, body))
        if body is None and url.endswith("/instances/minkops-books"):
            if self.existing is None:
                raise RuntimeError("Google API 404: sqladmin.googleapis.com/v1/projects/p/instances/minkops-books")
            return self.existing
        return {"name": "operation-1"}

    def wait(self, url, *, timeout=600):
        self.calls.append((url, "wait"))
        return {"done": True}


def test_a_missing_instance_is_created_as_encrypted_postgres_16_with_point_in_time_recovery():
    api = Api()
    assert provision_database.ensure_instance(api, "minkops-ai-prod", "minkops-books", "us-central1", "db-g1-small", 10)
    (_, body), = [call for call in api.calls if isinstance(call[1], dict)]
    settings = body["settings"]
    assert body["databaseVersion"] == "POSTGRES_16" and settings["tier"] == "db-g1-small"
    assert settings["backupConfiguration"]["pointInTimeRecoveryEnabled"] is True
    assert settings["ipConfiguration"] == {"ipv4Enabled": True, "sslMode": "ENCRYPTED_ONLY", "authorizedNetworks": []}
    assert settings["deletionProtectionEnabled"] is True
    assert api.calls[-1] == ("https://sqladmin.googleapis.com/v1/projects/minkops-ai-prod/operations/operation-1", "wait")


def test_an_existing_instance_is_left_unchanged_and_must_be_postgres_16():
    api = Api({"databaseVersion": "POSTGRES_16"})
    assert not provision_database.ensure_instance(api, "minkops-ai-prod", "minkops-books", "us-central1", "db-g1-small", 10)
    assert all(body is None for _, body in api.calls)
    with pytest.raises(RuntimeError, match="not PostgreSQL 16"):
        provision_database.ensure_instance(Api({"databaseVersion": "POSTGRES_15"}), "p", "minkops-books", "r", "t", 10)


def test_other_api_failures_are_never_mistaken_for_absence():
    class Failing(Api):
        def request(self, url, body=None, *, method=None):
            raise RuntimeError("Google API 403: sqladmin.googleapis.com")

    with pytest.raises(RuntimeError, match="403"):
        provision_database.ensure_instance(Failing(), "p", "minkops-books", "r", "t", 10)

