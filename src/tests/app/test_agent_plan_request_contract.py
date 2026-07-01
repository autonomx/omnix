from __future__ import annotations

from app.assist_core.agent_plan_request import agent_plan_request_payload
from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.service_bridge import service_bridge_payload


def test_plan_request_contract_keeps_review_gate_and_no_execution() -> None:
    payload = agent_plan_request_payload(
        "  review the next safe step  ",
        {"session_id": "s1", "mode": "rpg"},
    )

    assert payload["mode"] == "agent_mode"
    assert payload["objective"] == "review the next safe step"
    assert payload["context"] == {"session_id": "s1", "mode": "rpg"}
    assert payload["constraints"] == {
        "no_execution": True,
        "requires_review": True,
    }


def test_plan_request_contract_is_bridge_safe_when_disabled() -> None:
    request = agent_plan_request_payload("review", {"mode": "rpg"})
    bridge = service_bridge_payload(
        request,
        config=HermesSidecarConfig(False, "http://local", 5),
    )

    assert bridge["sent"] is False
    assert bridge["read_only"] is True
    assert bridge["executes"] is False
