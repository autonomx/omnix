from __future__ import annotations

from app.agent_runtime.router import route_omnix_request


def test_router_keeps_hermes_out_of_obvious_requests() -> None:
    assert route_omnix_request("Explain dependency injection").lane == "chat"
    direct = route_omnix_request("Turn off the desk plug")
    assert direct.lane == "direct"
    assert direct.hermes_recommended is False
    explicit = route_omnix_request("/agent fix these tests")
    assert explicit.lane == "agent"
    assert explicit.hermes_recommended is False


def test_router_uses_hermes_only_as_semantic_adviser_for_broad_tasks() -> None:
    decision = route_omnix_request("Take care of anything important before I leave for a week")
    assert decision.lane == "agent"
    assert decision.hermes_recommended is True


def test_router_recognizes_known_workflow_without_llm() -> None:
    decision = route_omnix_request(
        "Run my bedtime routine",
        workflow_lookup=lambda name: "bedtime-v1" if "bedtime" in name else None,
    )
    assert decision.lane == "workflow"
    assert decision.workflow_id == "bedtime-v1"
