from __future__ import annotations

from app.assist_core.core import AssistantResult, ToolCall, ToolResult, ToolRiskLevel
from app.assist_core.live_agent_planner import LiveAgentUnavailable, plan_live_agent_proposal
from app.assistant_tools.hermes_payloads import HermesAssistantToolExecutePayload
from app.assistant_tools.models import AssistantToolResult, AssistantToolReviewDecision


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


class FakeKasaReadHermesClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def plan(self, request):
        return AssistantResult(
            success=True,
            response="I will check the plug.",
            domain="house",
            tool_calls=[
                ToolCall(
                    name="kasa_get_state",
                    args={"target": "Desk Plug"},
                    risk=ToolRiskLevel.LOW,
                )
            ],
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


def test_live_agent_planner_executes_only_governed_kasa_reads(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_ENABLED", "1")
    monkeypatch.setattr(
        "app.assist_core.live_agent_planner.HermesSidecarClient",
        FakeKasaReadHermesClient,
    )

    def execute(user_request, request):
        assert user_request == "Is the Kasa desk plug on?"
        assert request.tool_id == "kasa"
        assert request.action_id == "kasa.get_state"
        assert request.approved is False
        return HermesAssistantToolExecutePayload(
            user_request=user_request,
            selected_tool_id="kasa",
            selected_action_id="kasa.get_state",
            approval_decision=AssistantToolReviewDecision(
                tool_id="kasa",
                action_id="kasa.get_state",
                session_id="chat:test",
                allowed=True,
                executable=True,
                approval_required=False,
                risk_level="low",
                state_changed=False,
                result_summary="Ready to run Read plug state.",
            ),
            execution_result=AssistantToolResult(
                tool_id="kasa",
                action_id="kasa.get_state",
                session_id="chat:test",
                risk_level="low",
                state_changed=False,
                result_summary="Desk Plug is on.",
                output={"device": {"alias": "Desk Plug", "is_on": True}},
            ),
            state_changed=False,
        )

    monkeypatch.setattr(
        "app.assist_core.live_agent_planner.hermes_assistant_tool_execute_payload",
        execute,
    )

    response = plan_live_agent_proposal(
        content="Is the Kasa desk plug on?",
        session_id="chat:test",
    )

    assert response.result["response"] == "Desk Plug is on."
    assert response.result["requires_confirmation"] is False
    assert response.result["tool_results"][0]["name"] == "kasa_get_state"
    assert response.result["tool_results"][0]["executed"] is True


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
