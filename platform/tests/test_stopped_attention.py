"""Stopping retains unresolved business inputs without repeating settled items."""

from unittest.mock import patch

from minkops_platform.accounts.attention import stopped


def test_stopped_attention_retains_unresolved_and_unsaved_proposals_once():
    run = {"result": {"records": [
        {"source_file_id": "saved", "status": "saved"},
        {"source_file_id": "duplicate", "status": "duplicate"},
        {"source_file_id": "rejected", "status": "rejected"},
        {"source_file_id": "pending", "status": "writing"},
    ], "unresolved": [
        {"source_file_id": "pending", "reason": "Needs a destination"},
        {"source_file_id": "unread", "reason": "Could not read bill"},
    ]}}
    with patch("minkops_platform.accounts.attention.flag", return_value={"id": "item"}) as flag, \
         patch("minkops_platform.attention.audit") as audit:
        stopped(None, run, "operator")
    assert [call.args[2]["source_file_id"] for call in flag.call_args_list] == ["pending", "unread"]
    assert all(call.kwargs["actor"] == "operator" for call in flag.call_args_list)
    assert audit.call_count == 2
    assert all(call.args[2:4] == ("operator", "stopped") for call in audit.call_args_list)


def test_stopping_before_result_does_not_invent_a_business_proposal():
    with patch("minkops_platform.accounts.attention.flag") as flag:
        stopped(None, {"result": None}, "operator")
    flag.assert_not_called()
