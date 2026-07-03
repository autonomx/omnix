"""Backend mirror of the Chat assistant tool registry."""
from __future__ import annotations

from .models import AssistantToolAction, AssistantToolRegistryPayload, AssistantToolSpec, ApprovalPolicy, ToolActionCategory, ToolRiskLevel
from .validation import is_valid_action_id, is_valid_tool_id


def default_approval_policy_for_action(
    *,
    category: ToolActionCategory,
    risk_level: ToolRiskLevel,
    requires_confirmation: bool = False,
    is_destructive: bool = False,
) -> ApprovalPolicy:
    if is_destructive or category == "delete":
        return "always_ask"
    if requires_confirmation or risk_level == "high":
        return "always_ask"
    if category in {"write", "execute"} or risk_level == "medium":
        return "ask_sensitive"
    return "allow_automatic"


def tool_action(
    *,
    tool_id: str,
    action_id: str,
    label: str,
    description: str,
    category: ToolActionCategory,
    risk_level: ToolRiskLevel = "low",
    enabled: bool = True,
    requires_connection: bool = True,
    requires_confirmation: bool = False,
    is_destructive: bool = False,
    approval_policy: ApprovalPolicy | None = None,
) -> AssistantToolAction:
    if not is_valid_tool_id(tool_id):
        raise ValueError(f"invalid tool id: {tool_id}")
    if not is_valid_action_id(action_id):
        raise ValueError(f"invalid action id: {action_id}")
    if not action_id.startswith(f"{tool_id}."):
        raise ValueError(f"action {action_id} does not belong to tool {tool_id}")
    return AssistantToolAction(
        id=action_id,
        tool_id=tool_id,
        label=label,
        description=description,
        category=category,
        risk_level=risk_level,
        enabled=enabled,
        approval_policy=approval_policy
        or default_approval_policy_for_action(
            category=category,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            is_destructive=is_destructive,
        ),
        requires_connection=requires_connection,
        requires_confirmation=requires_confirmation,
        is_destructive=is_destructive,
    )


def default_assistant_tools() -> list[AssistantToolSpec]:
    """Return the canonical backend registry for Chat assistant tools."""

    return [
        AssistantToolSpec(
            id="gmail",
            name="Gmail",
            description="Read, draft, send, and delete Gmail messages with approval controls.",
            category="communication",
            provider="Google",
            actions=[
                tool_action(
                    tool_id="gmail",
                    action_id="gmail.read_email",
                    label="Read email",
                    description="Search and read Gmail messages and threads.",
                    category="read",
                ),
                tool_action(
                    tool_id="gmail",
                    action_id="gmail.create_draft",
                    label="Create drafts",
                    description="Create reviewable Gmail drafts without sending.",
                    category="write",
                    risk_level="medium",
                ),
                tool_action(
                    tool_id="gmail",
                    action_id="gmail.send_email",
                    label="Send email",
                    description="Send or reply to Gmail messages.",
                    category="write",
                    risk_level="high",
                    requires_confirmation=True,
                ),
                tool_action(
                    tool_id="gmail",
                    action_id="gmail.delete_email",
                    label="Delete email",
                    description="Move Gmail messages to Trash.",
                    category="delete",
                    risk_level="high",
                    enabled=False,
                    requires_confirmation=True,
                    is_destructive=True,
                ),
            ],
        ),
        AssistantToolSpec(
            id="calendar",
            name="Google Calendar",
            description="Read availability and manage calendar events.",
            category="productivity",
            provider="Google",
            actions=[
                tool_action(
                    tool_id="calendar",
                    action_id="calendar.read_availability",
                    label="Read availability",
                    description="Read calendar availability and event summaries.",
                    category="read",
                ),
                tool_action(
                    tool_id="calendar",
                    action_id="calendar.create_event",
                    label="Create events",
                    description="Create Google Calendar events.",
                    category="write",
                    risk_level="medium",
                    requires_confirmation=True,
                ),
                tool_action(
                    tool_id="calendar",
                    action_id="calendar.delete_event",
                    label="Delete events",
                    description="Delete Google Calendar events.",
                    category="delete",
                    risk_level="high",
                    requires_confirmation=True,
                    is_destructive=True,
                ),
            ],
        ),
        AssistantToolSpec(
            id="contacts",
            name="Google Contacts",
            description="Resolve contacts for email and calendar workflows.",
            category="productivity",
            provider="Google",
            actions=[
                tool_action(
                    tool_id="contacts",
                    action_id="contacts.search_contacts",
                    label="Search contacts",
                    description="Search Google Contacts to resolve people and email addresses.",
                    category="read",
                ),
                tool_action(
                    tool_id="contacts",
                    action_id="contacts.resolve_recipient",
                    label="Resolve recipients",
                    description="Use contact details to address emails or calendar invites.",
                    category="read",
                    risk_level="medium",
                ),
            ],
        ),
        AssistantToolSpec(
            id="github",
            name="GitHub",
            description="Read repositories, manage pull requests, inspect CI, and perform governed repo actions.",
            category="development",
            provider="GitHub",
            actions=[
                tool_action(
                    tool_id="github",
                    action_id="github.read_repo",
                    label="Read repositories",
                    description="Read repository metadata, files, pull requests, and checks.",
                    category="read",
                ),
                tool_action(
                    tool_id="github",
                    action_id="github.create_branch",
                    label="Create branches",
                    description="Create GitHub branches for implementation work.",
                    category="write",
                    risk_level="medium",
                ),
                tool_action(
                    tool_id="github",
                    action_id="github.create_pr",
                    label="Open pull requests",
                    description="Open pull requests from prepared branch changes.",
                    category="write",
                    risk_level="medium",
                ),
                tool_action(
                    tool_id="github",
                    action_id="github.merge_pr",
                    label="Merge pull requests",
                    description="Merge pull requests after required checks pass.",
                    category="write",
                    risk_level="high",
                    requires_confirmation=True,
                ),
            ],
        ),
    ]


def assistant_tool_registry_payload(tools: list[AssistantToolSpec] | None = None) -> AssistantToolRegistryPayload:
    registry_tools = tools or default_assistant_tools()
    return AssistantToolRegistryPayload(
        tools=registry_tools,
        actions=[action for tool in registry_tools for action in tool.actions],
    )


def get_registered_tool(tool_id: str, tools: list[AssistantToolSpec] | None = None) -> AssistantToolSpec | None:
    return next((tool for tool in (tools or default_assistant_tools()) if tool.id == tool_id), None)


def get_registered_action(action_id: str, tools: list[AssistantToolSpec] | None = None) -> AssistantToolAction | None:
    return next((action for tool in (tools or default_assistant_tools()) for action in tool.actions if action.id == action_id), None)
