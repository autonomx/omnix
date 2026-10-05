"""Chat's live agent plans with tools through the LIVE_AGENT_TOOLS port (PA-1.3)."""
from __future__ import annotations

import pytest

from app.assistant_tools.live_agent_proposals import AssistantLiveAgentTools
from app.assistant_tools.models import AssistantToolRequest
from app.capabilities.executor import LIVE_AGENT_TOOLS, live_agent_tools
from app.runtime.ports import PortBinding, PortBindings, install_port_bindings


def test_without_assistant_tools_the_live_agent_plans_with_no_tools() -> None:
    install_port_bindings(PortBindings({}))
    tools = live_agent_tools()

    assert tools.read_tool_names == frozenset() and tools.is_device_tool("kasa.get_state") is False
    assert tools.planner_context() == {} and tools.first_pending_write({"tool_calls": []}, session_id="s") is None
    assert tools.tool_proposals(user_request="hi", session_id="s", source_message_id="m", mode_result={}) == []
    with pytest.raises(ValueError):
        tools.parse_request({"tool_id": "kasa", "action_id": "kasa.turn_on"})


def test_assistant_tools_provide_the_device_reads_and_parse_pending_requests() -> None:
    install_port_bindings(PortBindings.build([
        PortBinding(LIVE_AGENT_TOOLS, AssistantLiveAgentTools(), owner="assistant-tools"),
    ]))
    tools = live_agent_tools()

    assert "kasa.get_state" in tools.read_tool_names
    assert set(tools.planner_context()) >= {"current_datetime", "user_timezone"}
    parsed = tools.parse_request({"tool_id": "kasa", "action_id": "kasa.turn_on", "input": {"target": "lamp"}})
    assert isinstance(parsed, AssistantToolRequest) and parsed.action_id == "kasa.turn_on"
    with pytest.raises(ValueError):
        tools.parse_request({"unexpected": True})
