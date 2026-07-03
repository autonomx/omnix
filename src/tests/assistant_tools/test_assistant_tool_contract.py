from app.assistant_tools import (
    AssistantToolAction,
    AssistantToolRequest,
    AssistantToolSpec,
    is_valid_action_id,
    is_valid_tool_id,
    validate_assistant_tool_request,
)


def _tool(*, enabled: bool = True, action_enabled: bool = True, approval_policy: str = "allow_automatic") -> AssistantToolSpec:
    return AssistantToolSpec(
        id="gmail",
        name="Gmail",
        description="Gmail actions",
        category="communication",
        enabled=enabled,
        connection_status="connected",
        actions=[
            AssistantToolAction(
                id="gmail.read_email",
                tool_id="gmail",
                label="Read email",
                description="Read email",
                category="read",
                risk_level="low",
                enabled=action_enabled,
                approval_policy=approval_policy,
            ),
            AssistantToolAction(
                id="gmail.send_email",
                tool_id="gmail",
                label="Send email",
                description="Send email",
                category="write",
                risk_level="high",
                enabled=action_enabled,
                approval_policy="always_ask",
                requires_confirmation=True,
            ),
        ],
    )


def test_tool_and_action_id_validators_accept_canonical_ids():
    assert is_valid_tool_id("gmail")
    assert is_valid_tool_id("google_contacts")
    assert is_valid_action_id("gmail.read_email")
    assert is_valid_action_id("github.create_pr")


def test_tool_and_action_id_validators_reject_unsafe_ids():
    assert not is_valid_tool_id("Gmail")
    assert not is_valid_tool_id("../gmail")
    assert not is_valid_action_id("gmail")
    assert not is_valid_action_id("gmail/read_email")
    assert not is_valid_action_id("gmail.ReadEmail")


def test_valid_read_request_is_executable_after_validation():
    result = validate_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email", session_id="chat:1"),
        [_tool()],
    )

    assert result.valid is True
    assert result.executable is True
    assert result.approval_required is False
    assert result.reason is None


def test_invalid_action_tool_mismatch_is_blocked():
    result = validate_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="github.read_repo"),
        [_tool()],
    )

    assert result.valid is False
    assert result.executable is False
    assert result.reason == "action_tool_mismatch"


def test_disabled_tool_request_is_blocked():
    result = validate_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email"),
        [_tool(enabled=False)],
    )

    assert result.valid is False
    assert result.reason == "tool_disabled"


def test_disabled_action_request_is_blocked():
    result = validate_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email"),
        [_tool(action_enabled=False)],
    )

    assert result.valid is False
    assert result.reason == "action_disabled"


def test_approval_required_request_is_not_executable_until_approved():
    pending = validate_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.send_email"),
        [_tool()],
    )
    approved = validate_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.send_email", approved=True),
        [_tool()],
    )

    assert pending.valid is True
    assert pending.approval_required is True
    assert pending.executable is False
    assert pending.reason == "approval_required"
    assert approved.valid is True
    assert approved.approval_required is True
    assert approved.executable is True
    assert approved.reason is None
