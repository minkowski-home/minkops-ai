"""Bounded display measurements cannot alter catalog completion or grow task logs."""
import pytest
from minkops_platform import discovery
from minkops_platform.errors import ServiceError


class Connection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, args):
        self.calls.append((sql, args))


def test_measurement_replaces_activity_without_appending_a_task_event(monkeypatch):
    row = {"id": "run", "observations": [{"key": "tally", "status": "reading", "category": "A"}]}
    monkeypatch.setattr(discovery, "get_run", lambda *args: row)
    monkeypatch.setattr(discovery, "plan", lambda *args: {"sources": [{"key": "tally"}]})
    monkeypatch.setattr(discovery, "_observe", lambda *args: pytest.fail("progress-only updates must not grow the task timeline"))
    connection = Connection()
    value = discovery.progress(connection, {"tenant_id": "tenant"}, {"id": "job", "input": {"discovery_run_id": "run"}}, {
        "source_key": "tally", "status": "reading", "category": "A",
        "progress": {"completed": 2, "total": 7, "activity": "Collected masters", "item": "A"}
    })
    assert len(value["observations"]) == 1
    assert value["observations"][0]["progress"]["completed"] == 2
    assert len(connection.calls) == 2


@pytest.mark.parametrize("measurement", [
    {"completed": 8, "total": 7, "activity": "Collected masters"},
    {"completed": -1, "total": 7, "activity": "Collected masters"},
    {"completed": True, "total": 7, "activity": "Collected masters"},
    {"completed": 0, "total": 10001, "activity": "Collected masters"},
    {"completed": 0, "total": 7, "activity": "Run arbitrary command"},
    {"completed": 0, "total": 7, "activity": "Collected masters", "item": "x" * 501},
])
def test_invalid_measurements_are_rejected_before_any_update(monkeypatch, measurement):
    monkeypatch.setattr(discovery, "get_run", lambda *args: {"id": "run", "observations": []})
    monkeypatch.setattr(discovery, "plan", lambda *args: {"sources": [{"key": "tally"}]})
    connection = Connection()
    with pytest.raises(ServiceError, match="progress"):
        discovery.progress(connection, {"tenant_id": "tenant"}, {"id": "job", "input": {"discovery_run_id": "run"}}, {"source_key": "tally", "status": "reading", "progress": measurement})
    assert not connection.calls


def test_status_summaries_are_readable_text(monkeypatch):
    """Progress summaries reach users verbatim; mis-encoded literals must not ship."""
    row = {"id": "run", "observations": []}
    observed = []
    monkeypatch.setattr(discovery, "get_run", lambda *args: row)
    monkeypatch.setattr(discovery, "plan", lambda *args: {"sources": [{"key": "tally"}]})
    monkeypatch.setattr(discovery, "_observe", lambda connection, row, state, summary, progress: observed.append(summary))
    discovery.progress(Connection(), {"tenant_id": "tenant"}, {"id": "job", "input": {"discovery_run_id": "run"}},
                       {"source_key": "tally", "status": "reading"})
    assert observed == ["Tally: Reading your selected source…"]
