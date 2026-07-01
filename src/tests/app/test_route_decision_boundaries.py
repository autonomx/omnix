from __future__ import annotations

from app.assist_core.agent_plan_request import agent_plan_request_payload
from app.assist_core.omnix_mode_router import omnix_mode_route
from app.assist_core.route_decision_bridge import route_decision_bridge_payload


def test_route_decision_and_plan_request_require_review() -> None:
    decision = route_decision_bridge_payload(
        {
            "ok": True,
            "item_id": "plan-1",
            "summary": "Ready for review.",
            "review": True,
        }
    )
    request = agent_plan_request_payload("review", {"mode": "rpg"})

    assert decision["route"]["requires_review"] is True
    assert decision["review_required"] is True
    assert decision["executes"] is False
    assert request["constraints"] == {
        "no_execution": True,
        "requires_review": True,
    }


def test_rpg_route_remains_simulation_owned() -> None:
    route = omnix_mode_route("rpg")

    assert route["execution_owner"] == "rpg_sim"
    assert route["hermes_role"] == "suggest"
    assert route["direct_provider_path"] is False
