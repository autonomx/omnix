"""Persistent assistant tool configuration with safe defaults."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from .credentials import delete_tool_credential
from .models import ApprovalPolicy, ConnectionStatus
from .registry import default_assistant_tools

DEFAULT_CONFIG_PATH = Path("resources/data/assistant_tools_config.json")


class AssistantActionConfigRecord(BaseModel):
    action_id: str
    enabled: bool = True
    approval_policy: ApprovalPolicy = "allow_automatic"


class AssistantToolConfigRecord(BaseModel):
    tool_id: str
    enabled: bool = False
    connection_status: ConnectionStatus = "not_configured"
    account_label: str | None = None
    account_email: str | None = None
    connected_at: str | None = None
    approval_policy: ApprovalPolicy | None = None
    actions: list[AssistantActionConfigRecord] = Field(default_factory=list)


class AssistantToolsConfigPayload(BaseModel):
    tools: list[AssistantToolConfigRecord]


def assistant_tool_config_path() -> Path:
    configured = os.environ.get("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH")
    return Path(configured) if configured else DEFAULT_CONFIG_PATH


def _default_action_enabled(action_id: str, category: str, is_destructive: bool) -> bool:
    return False if is_destructive or category == "delete" else True


def default_assistant_tools_config() -> AssistantToolsConfigPayload:
    tools: list[AssistantToolConfigRecord] = []
    for tool in default_assistant_tools():
        actions = [
            AssistantActionConfigRecord(
                action_id=action.id,
                enabled=_default_action_enabled(action.id, action.category, action.is_destructive),
                approval_policy=action.approval_policy,
            )
            for action in tool.actions
        ]
        tools.append(
            AssistantToolConfigRecord(
                tool_id=tool.id,
                enabled=False,
                connection_status="not_configured",
                actions=actions,
            )
        )
    return AssistantToolsConfigPayload(tools=tools)


def _merge_known_config(payload: AssistantToolsConfigPayload) -> AssistantToolsConfigPayload:
    defaults = default_assistant_tools_config()
    incoming_tools = {tool.tool_id: tool for tool in payload.tools}
    merged_tools: list[AssistantToolConfigRecord] = []
    for default_tool in defaults.tools:
        incoming_tool = incoming_tools.get(default_tool.tool_id)
        if incoming_tool is None:
            merged_tools.append(default_tool)
            continue
        incoming_actions = {action.action_id: action for action in incoming_tool.actions}
        merged_actions = [incoming_actions.get(action.action_id, action) for action in default_tool.actions]
        merged_tools.append(
            AssistantToolConfigRecord(
                tool_id=default_tool.tool_id,
                enabled=incoming_tool.enabled,
                connection_status=incoming_tool.connection_status,
                account_label=incoming_tool.account_label,
                account_email=incoming_tool.account_email,
                connected_at=incoming_tool.connected_at,
                approval_policy=incoming_tool.approval_policy,
                actions=merged_actions,
            )
        )
    return AssistantToolsConfigPayload(tools=merged_tools)


def load_assistant_tools_config(path: Path | None = None) -> AssistantToolsConfigPayload:
    config_path = path or assistant_tool_config_path()
    if not config_path.exists():
        return default_assistant_tools_config()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_assistant_tools_config()
    return _merge_known_config(AssistantToolsConfigPayload.model_validate(data))


def save_assistant_tools_config(payload: AssistantToolsConfigPayload, path: Path | None = None) -> AssistantToolsConfigPayload:
    config_path = path or assistant_tool_config_path()
    normalized = _merge_known_config(payload)
    if path is None:
        for tool in normalized.tools:
            if tool.connection_status != "connected":
                delete_tool_credential(tool.tool_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(normalized.model_dump_json(indent=2), encoding="utf-8")
    return normalized
