"""The active-time budget belongs to the platform, not a workflow skill."""
from unittest.mock import Mock, patch

import pytest


def test_default_and_configured_budget_reject_invalid_operator_settings():
    from minkops_platform.run_limits import limit_minutes
    with patch.dict('os.environ', {}, clear=True):
        assert limit_minutes() == 45
    for value in ('1', '90'):
        with patch.dict('os.environ', {'MINKOPS_RUN_TIMEOUT_MINUTES': value}):
            assert limit_minutes() == int(value)
    for value in ('0', '-1', '1.5', 'disabled', '1441'):
        with patch.dict('os.environ', {'MINKOPS_RUN_TIMEOUT_MINUTES': value}), pytest.raises(ValueError):
            limit_minutes()


def test_cancellation_uses_the_documented_event_and_skips_finished_turns():
    from minkops_platform.runtime.openai_hosted import cancel_turn
    client = Mock()
    client.beta.agents.sessions.turns.retrieve.return_value.status = 'in_progress'
    cancel_turn('session', 'turn', client=client)
    client.beta.agents.sessions.events.create.assert_called_once_with(
        'session', events=[{'type': 'agent.session.input.cancel'}])
    client.beta.agents.sessions.events.create.reset_mock()
    for status in ('completed', 'failed', 'cancelled'):
        client.beta.agents.sessions.turns.retrieve.return_value.status = status
        cancel_turn('session', 'turn', client=client)
    client.beta.agents.sessions.events.create.assert_not_called()
