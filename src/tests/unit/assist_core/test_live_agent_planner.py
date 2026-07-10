from __future__ import annotations

from app.assist_core.core import AssistantResult, ToolResult
from app.assist_core.live_agent_planner import LiveAgentUnavailable, plan_live_agent_proposal


class FakeHermesClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def plan(self, request):
        assert request.dry_run is True
        assert request.metadata["proposal_only"] is True
        assert request.metadata["review_required"] is True
        assert request.metadata["executes"] is False
        return AssistantResult(
            success=True,
            response="Review this proposal.",
            domain="chat",
            tool_results=[ToolResult(name="fake", ok=True, executed=True)],
        )


class OfflineHermesClient:
    def __init__(self, **kwargs) -> None:
        pass

    def plan(self, request):
        raise OSError("offline")


def test_live_agent_planner_forces_nonexecuting_review_proposal(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_ENABLED", "1")
    monkeypatch.setattr(
        "app.assist_core.live_agent_planner.HermesSidecarClient",
        FakeHermesClient,
    )

    response = plan_live_agent_proposal(
        content="Send the message",
        session_id="chat:test",
        timeout_seconds=3,
    )

    assert response.backend == "hermes"
    assert response.result["requires_confirmation"] is True
    assert response.result["tool_results"][0]["executed"] is False


def test_live_agent_planner_reports_unavailability_for_provider_fallback(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_ENABLED", "1")
    monkeypatch.setattr(
        "app.assist_core.live_agent_planner.HermesSidecarClient",
        OfflineHermesClient,
    )

    try:
        plan_live_agent_proposal(
            content="Schedule the meeting",
            session_id="chat:test",
        )
    except LiveAgentUnavailable as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("expected LiveAgentUnavailable")
