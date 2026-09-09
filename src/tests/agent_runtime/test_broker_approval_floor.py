from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.agent_runtime.broker_api import (
    BrokerCapabilityRequest,
    _normalize_capability_input,
    _review_with_run_policy,
)
from app.assistant_tools.models import (
    AssistantToolRequest,
    AssistantToolReviewDecision,
)


def _decision(*, approval_required: bool, allowed: bool = True):
    return AssistantToolReviewDecision(
        tool_id="home",
        action_id="home.set_state",
        allowed=allowed,
        executable=allowed and not approval_required,
        approval_required=approval_required,
    )


def test_run_policy_never_weakens_canonical_approval() -> None:
    request = AssistantToolRequest(
        tool_id="home",
        action_id="home.set_state",
        input={"target": "Desk", "state": "off"},
    )
    with patch(
        "app.agent_runtime.broker_api.review_assistant_tool_request",
        return_value=_decision(approval_required=True),
    ) as review:
        effective, decision = _review_with_run_policy(
            request,
            "allow_automatic",
        )
    assert decision.approval_required is True
    assert effective.approval_policy is None
    review.assert_called_once()


def test_run_policy_can_make_automatic_action_stricter() -> None:
    request = AssistantToolRequest(
        tool_id="github",
        action_id="github.read_repo",
        input={"repository": "autonomx/omnix"},
    )
    automatic = AssistantToolReviewDecision(
        tool_id="github",
        action_id="github.read_repo",
        allowed=True,
        executable=True,
        approval_required=False,
    )
    stricter = automatic.model_copy(
        update={"executable": False, "approval_required": True}
    )
    with patch(
        "app.agent_runtime.broker_api.review_assistant_tool_request",
        side_effect=[automatic, stricter],
    ):
        effective, decision = _review_with_run_policy(
            request,
            "always_ask",
        )
    assert effective.approval_policy == "always_ask"
    assert decision.approval_required is True


def test_sensitive_run_policy_preserves_governed_browser_automatic_policy() -> None:
    request = AssistantToolRequest(
        tool_id="browser",
        action_id="browser.click",
        input={"selector": "@e1"},
    )
    automatic = AssistantToolReviewDecision(
        tool_id="browser",
        action_id="browser.click",
        allowed=True,
        executable=True,
        approval_required=False,
    )
    with patch(
        "app.agent_runtime.broker_api.review_assistant_tool_request",
        return_value=automatic,
    ) as review:
        effective, decision = _review_with_run_policy(
            request,
            "ask_sensitive",
        )

    assert effective.approval_policy is None
    assert decision.approval_required is False
    review.assert_called_once()


def test_browser_text_assertion_alias_is_canonicalized_before_execution() -> None:
    request = _normalize_capability_input(
        "browser.assert_text_contains",
        BrokerCapabilityRequest(
            input={"selector": "#status", "expected_text": "Character Settings"},
        ),
    )

    assert request.input == {
        "selector": "#status",
        "expected": "Character Settings",
    }


def test_invalid_browser_assertion_is_rejected_before_execution() -> None:
    with pytest.raises(HTTPException) as raised:
        _normalize_capability_input(
            "browser.assert_text_contains",
            BrokerCapabilityRequest(input={"selector": "#status"}),
        )

    assert raised.value.status_code == 422
    assert raised.value.detail == "agent_browser_assertion_missing_input:expected"
