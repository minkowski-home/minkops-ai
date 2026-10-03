import asyncio

import pytest

from minkops_connectors.workspace_smtp import (
    SmtpConfigurationError,
    SmtpOutcomeUncertain,
)
from minkops_platform import interest_delivery


def submission(**overrides):
    return interest_delivery.InterestSubmission(
        name="Alex Visitor",
        email="alex@example.com",
        company="Example Co",
        interest="operations",
        message="Need help with reports.",
        **overrides,
    )


def test_identical_accepted_submission_is_sent_once(monkeypatch):
    calls = []

    async def send(**payload):
        calls.append(payload)
        await asyncio.sleep(0.01)
        return "<example@minkops.com>"

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", send)
    guard = interest_delivery.DeliveryGuard()

    async def submit_twice():
        await asyncio.gather(
            guard.send(submission(), "same-key"),
            guard.send(submission(), "same-key"),
        )

    asyncio.run(submit_twice())
    assert len(calls) == 1


def test_uncertain_attempt_blocks_automatic_resend(monkeypatch):
    calls = 0

    async def uncertain(**_payload):
        nonlocal calls
        calls += 1
        raise SmtpOutcomeUncertain()

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", uncertain)
    guard = interest_delivery.DeliveryGuard()

    async def submit_twice():
        with pytest.raises(interest_delivery.DeliveryError) as first:
            await guard.send(submission(), "same-key")
        with pytest.raises(interest_delivery.DeliveryError) as retry:
            await guard.send(submission(), "same-key")
        return first.value, retry.value

    first, retry = asyncio.run(submit_twice())
    assert first.ambiguous is True
    assert retry.ambiguous is True
    assert calls == 1


def test_missing_configuration_is_a_safe_retryable_failure(monkeypatch):
    async def unconfigured(**_payload):
        raise SmtpConfigurationError()

    monkeypatch.setattr(interest_delivery, "send_discovery_notification", unconfigured)

    with pytest.raises(interest_delivery.DeliveryError) as error:
        asyncio.run(interest_delivery.deliver_interest(submission()))

    assert error.value.ambiguous is False
    assert str(error.value) == "Email delivery is not configured"
