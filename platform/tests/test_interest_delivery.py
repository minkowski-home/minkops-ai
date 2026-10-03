import asyncio

import pytest

from minkops_connectors import workspace_smtp
from minkops_platform import interest_delivery


@pytest.fixture
def submission():
    return interest_delivery.InterestSubmission(
        name="Alex Visitor",
        email="alex@example.test",
        company="Example Co",
        interest="operations",
        message="A short inquiry",
    )


def test_identical_submission_is_sent_once(monkeypatch, submission):
    calls = []

    async def fake_send(**kwargs):
        calls.append(kwargs)
        return "<test@minkops.com>"

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", fake_send)
    guard = interest_delivery.DeliveryGuard()

    async def run():
        await guard.send(submission, "same-key")
        await guard.send(submission, "same-key")

    asyncio.run(run())
    assert len(calls) == 1


def test_ambiguous_smtp_acceptance_blocks_automatic_retry(monkeypatch, submission):
    calls = 0

    async def uncertain(**_kwargs):
        nonlocal calls
        calls += 1
        raise workspace_smtp.SmtpOutcomeUncertain("safe message")

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", uncertain)
    guard = interest_delivery.DeliveryGuard()

    async def run():
        with pytest.raises(interest_delivery.DeliveryError) as first:
            await guard.send(submission, "same-key")
        assert first.value.ambiguous
        with pytest.raises(interest_delivery.DeliveryError) as retry:
            await guard.send(submission, "same-key")
        assert retry.value.ambiguous

    asyncio.run(run())
    assert calls == 1


def test_missing_smtp_configuration_fails_closed(monkeypatch, submission):
    async def unconfigured(**_kwargs):
        raise workspace_smtp.SmtpConfigurationError("private configuration")

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", unconfigured)
    guard = interest_delivery.DeliveryGuard()

    with pytest.raises(interest_delivery.DeliveryError) as error:
        asyncio.run(guard.send(submission, "same-key"))
    assert not error.value.ambiguous
    assert "private configuration" not in str(error.value)


@pytest.mark.parametrize(
    "failure",
    [workspace_smtp.SmtpSetupFailure, workspace_smtp.SmtpRejected],
)
def test_pre_acceptance_failure_is_not_marked_ambiguous(monkeypatch, submission, failure):
    async def reject(**_kwargs):
        raise failure("private diagnostic")

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", reject)
    guard = interest_delivery.DeliveryGuard()

    with pytest.raises(interest_delivery.DeliveryError) as error:
        asyncio.run(guard.send(submission, "same-key"))
    assert not error.value.ambiguous
