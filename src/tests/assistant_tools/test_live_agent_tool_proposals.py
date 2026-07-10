from __future__ import annotations

from app.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
    save_assistant_tools_config,
)
from app.assistant_tools.live_agent_proposals import live_agent_tool_proposals


def _connected_config(tool_id: str) -> AssistantToolsConfigPayload:
    defaults = default_assistant_tools_config()
    return AssistantToolsConfigPayload(
        tools=[
            AssistantToolConfigRecord(
                tool_id=tool.tool_id,
                enabled=tool.tool_id == tool_id,
                connection_status="connected" if tool.tool_id == tool_id else "not_configured",
                actions=tool.actions,
            )
            for tool in defaults.tools
        ]
    )


def test_ambiguous_reminder_becomes_clarification_preview(monkeypatch, tmp_path) -> None:
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("calendar"), path)

    proposals = live_agent_tool_proposals(
        user_request="Create a reminder for six.",
        session_id="chat:1",
        source_message_id="message:1",
        mode_result={"tool_calls": []},
    )

    assert proposals[0]["action_id"] == "calendar.create_event"
    assert proposals[0]["ready_for_approval"] is False
    assert proposals[0]["missing_fields"] == ["end_time", "start_time"]
    assert proposals[0]["executes"] is False


def test_complete_calendar_call_is_ready_but_never_executes(monkeypatch, tmp_path) -> None:
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("calendar"), path)

    proposals = live_agent_tool_proposals(
        user_request="Schedule planning tomorrow at nine.",
        session_id="chat:1",
        source_message_id="message:1",
        mode_result={
            "tool_calls": [
                {
                    "name": "calendar.create_event",
                    "args": {
                        "title": "Planning",
                        "start_time": "2026-07-10T09:00:00-07:00",
                        "end_time": "2026-07-10T09:30:00-07:00",
                        "timezone": "America/Vancouver",
                    },
                    "reason": "Create the requested event after review.",
                }
            ]
        },
    )

    assert proposals[0]["ready_for_approval"] is True
    assert proposals[0]["approval_required"] is True
    assert proposals[0]["executes"] is False


def test_disconnected_calendar_proposal_routes_to_configuration(monkeypatch, tmp_path) -> None:
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(default_assistant_tools_config(), path)

    proposal = live_agent_tool_proposals(
        user_request="Schedule planning tomorrow at nine.",
        session_id="chat:1",
        source_message_id="message:1",
        mode_result={"tool_calls": []},
    )[0]

    assert proposal["connection_required"] is True
    assert proposal["ready_for_approval"] is False
