from __future__ import annotations

from app.assist_core.route_decision_bridge import route_decision_bridge_payload


def test_route_decision_bridge_is_proposal_only() -> None:
    payload = route_decision_bridge_payload(
        {
            "ok": True,
            "item_id": "plan-1",
            "summary": "Ready for review.",
            "review": True,
        }
    )

    assert payload["mode"] == "agent_mode"
    assert payload["route"]["path"] == "agent_plan"
    assert payload["route"]["read_only"] is True
    assert payload["route"]["executes"] is False
    assert payload["route"]["requires_review"] is True
    assert payload["display"] == {
        "ok": True,
        "item_id": "plan-1",
        "summary": "Ready for review.",
        "review": True,
    }
    assert payload["proposal_only"] is True
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
