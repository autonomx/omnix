"""A capability added by the recipe in AGENT_EXTENSION_GUIDE.md works end to end (WP-8.2)."""
from __future__ import annotations

from types import MappingProxyType

import pytest

from app.agent_runtime import profiles
from app.agent_runtime.profiles import get_agent_profile, resolve_profile_capabilities
from app.assistant_tools import AssistantToolRequest, review_assistant_tool_request
from app.assistant_tools import executor
from app.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
)
from app.assistant_tools.models import AssistantToolResult
from app.assistant_tools.registry import default_assistant_tools
from app.capabilities import registry


def _run_acme(request: AssistantToolRequest) -> AssistantToolResult:
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        result_summary="Found Acme record 42.",
        output={"record_id": request.input.get("record_id")},
    )


@pytest.fixture
def acme(monkeypatch):
    # Step 1: one declaration.
    declaration = registry._cap(
        "acme.lookup",
        "Look up an Acme record",
        "Read one Acme record by id.",
        zone="broker",
        effect="read",
        network=True,
        connection=True,
        provider="Acme",
        category="productivity",
        assistant=True,
        input_schema={"record_id": "string"},
    )
    monkeypatch.setattr(registry, "_DEFAULT_CAPABILITIES", (*registry._DEFAULT_CAPABILITIES, declaration))
    registry._capability_registry_for.cache_clear()
    yield declaration
    registry._capability_registry_for.cache_clear()


def _enabled(tool_id: str) -> AssistantToolsConfigPayload:
    payload = default_assistant_tools_config()
    return AssistantToolsConfigPayload(tools=[
        AssistantToolConfigRecord(**{
            **tool.model_dump(),
            "enabled": tool.tool_id == tool_id,
            "connection_status": "connected" if tool.tool_id == tool_id else tool.connection_status,
        })
        for tool in payload.tools
    ])


REQUEST = AssistantToolRequest(tool_id="acme", action_id="acme.lookup", input={"record_id": "42"})


def test_the_declaration_becomes_a_reviewed_tool_that_is_off_until_enabled(acme) -> None:
    tool = next(tool for tool in default_assistant_tools() if tool.id == "acme")
    assert [action.id for action in tool.actions] == ["acme.lookup"]

    assert review_assistant_tool_request(REQUEST, config=default_assistant_tools_config()).reason == "tool_disabled"
    decision = review_assistant_tool_request(REQUEST, config=_enabled("acme"))
    assert decision.executable and not decision.approval_required


def test_without_an_adapter_the_capability_fails_closed(acme) -> None:
    result = executor.run_capability_adapter(REQUEST, "low")

    assert result.error == "unknown_adapter"
    assert result.state_changed is False


def test_the_registered_adapter_runs_the_reviewed_request(acme, monkeypatch) -> None:
    # Step 2: one adapter registration.
    monkeypatch.setattr(executor, "ADAPTERS", MappingProxyType({**executor.ADAPTERS, "acme": _run_acme}))

    result = executor.run_capability_adapter(REQUEST, "low")

    assert result.error is None
    assert result.output == {"record_id": "42"}


def test_agents_receive_it_only_within_a_profile_ceiling(acme, monkeypatch) -> None:
    research = get_agent_profile("research")
    with pytest.raises(ValueError, match="exceed selected profile"):
        resolve_profile_capabilities(research, requested_external=["acme.lookup"])

    # Step 3 (optional): raise the ceiling of the profile that should use it.
    widened = research.model_copy(update={
        "optional_external_capabilities": (*research.optional_external_capabilities, "acme.lookup"),
    })
    monkeypatch.setitem(profiles._PROFILES, "research", widened)

    _local, external = resolve_profile_capabilities(get_agent_profile("research"), requested_external=["acme.lookup"])
    assert external == ["acme.lookup"]
