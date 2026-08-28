from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.profiles import (
    get_agent_profile,
    resolve_profile_capabilities,
)
from app.assistant_tools.config_store import default_assistant_tools_config
from app.assistant_tools.gate import review_assistant_tool_request
from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.research_adapter import run_research_tool_request


class _FakeResearchItem:
    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {
            "source_id": "web_search",
            "title": "Result",
            "content": "Grounded result",
            "url": "https://example.com/result",
            "metadata": {"provider": "test"},
        }


class _FakeResearchService:
    def search(self, query: str, max_results: int, *, identity: str):
        assert query == "latest agent runtime research"
        assert max_results == 3
        assert identity == "agent-session"
        return SimpleNamespace(
            items=[_FakeResearchItem()],
            diagnostics={"status": "completed", "provider": "test"},
            warnings=[],
            source_manifest_id="manifest-1",
        )


def test_research_profiles_are_read_only_external_authority_ceilings() -> None:
    research = get_agent_profile("research")
    local, external = resolve_profile_capabilities(research)
    assert local == []
    assert external == []
    assert research.requires_workspace is False

    trading = get_agent_profile("trading-research")
    local, external = resolve_profile_capabilities(trading)
    assert local == []
    assert external == ["research.web_search"]
    assert trading.requires_workspace is False
    _, issued = resolve_profile_capabilities(
        research,
        requested_external=["research.web_search"],
    )
    assert issued == ["research.web_search"]
    assert not any("order" in value or "trade" in value for value in trading.external_capabilities)


def test_research_tool_is_credentialless_enabled_and_automatic_by_default() -> None:
    config = default_assistant_tools_config()
    record = next(tool for tool in config.tools if tool.tool_id == "research")
    assert record.enabled is True
    assert record.connection_status == "connected"

    decision = review_assistant_tool_request(
        AssistantToolRequest(
            tool_id="research",
            action_id="research.web_search",
            input={"query": "topic"},
        ),
        config=config,
    )
    assert decision.allowed is True
    assert decision.executable is True
    assert decision.approval_required is False


def test_research_adapter_returns_grounded_read_only_results() -> None:
    request = AssistantToolRequest(
        tool_id="research",
        action_id="research.web_search",
        session_id="agent-session",
        input={
            "query": " latest   agent runtime research ",
            "max_results": 3,
        },
    )
    result = run_research_tool_request(
        request,
        service=_FakeResearchService(),
    )
    assert result.error is None
    assert result.state_changed is False
    assert result.output["source_manifest_id"] == "manifest-1"
    assert result.output["items"][0]["url"] == "https://example.com/result"
