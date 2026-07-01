from __future__ import annotations

from app.assist_core.agent_plan_request import agent_plan_request_payload


def test_plan_request_constraints() -> None:
    payload = agent_plan_request_payload("x")

    assert payload["mode"] == "agent_mode"
    assert payload["constraints"]["no_execution"] is True
    assert payload["constraints"]["requires_review"] is True
