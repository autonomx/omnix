from __future__ import annotations

from app.agent_runtime.broker_api import BrokerCapabilityRequest, _execution_key


def test_broker_proposal_ids_are_namespaced_by_run() -> None:
    request = BrokerCapabilityRequest(proposal_id="call-1", input={"target": "Desk"})
    assert _execution_key("run-a", "home.get_state", request) == "agent:run-a:call-1"
    assert _execution_key("run-b", "home.get_state", request) != _execution_key("run-a", "home.get_state", request)


def test_broker_fallback_identity_is_stable_for_same_input() -> None:
    request = BrokerCapabilityRequest(input={"target": "Desk"})
    first = _execution_key("run-a", "home.get_state", request)
    second = _execution_key("run-a", "home.get_state", request)
    assert first == second
