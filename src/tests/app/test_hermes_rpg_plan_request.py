from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.assist_core.hermes_rpg_plan import hermes_rpg_plan_payload
from app.assist_core.hermes_rpg_plan_request import request_hermes_rpg_plan
from app.assist_core.hermes_rpg_ticket import hermes_rpg_ticket_match, hermes_rpg_ticket_payload
from app.assist_core.hermes_rpg_validator import validate_hermes_rpg_proposal
from app.gateway.main import create_gateway_app


class FakePlanClient:
    def __init__(self, payload: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.payload = payload or {}
        self.error = error
        self.last_request: dict[str, Any] | None = None

    def rpg_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        self.last_request = request
        if self.error:
            raise self.error
        return self.payload


def test_hermes_rpg_plan_request_is_disabled_without_state_change() -> None:
    payload = request_hermes_rpg_plan({}, enabled=False)

    assert payload["ok"] is False
    assert payload["error"] == "hermes_disabled"
    assert payload["state_changed"] is False


def test_hermes_rpg_plan_request_normalizes_success_for_review() -> None:
    client = FakePlanClient({"command": "check inventory", "confidence": 0.7, "risk": "low"})
    payload = request_hermes_rpg_plan(
        {
            "session_id": "s1",
            "turn_id": 3,
            "context_hash": "abc",
            "context": {"available_commands": ["check"]},
        },
        client=client,
        enabled=True,
    )

    assert client.last_request is not None
    assert client.last_request["context_hash"] == "abc"
    assert payload["ok"] is True
    assert payload["mode"] == "review_required"
    assert payload["proposal"]["command"] == "check inventory"
    assert payload["state_changed"] is False


def test_hermes_rpg_plan_request_reports_unavailable_without_state_change() -> None:
    payload = request_hermes_rpg_plan({}, client=FakePlanClient(error=RuntimeError("offline")), enabled=True)

    assert payload["ok"] is False
    assert payload["error"] == "hermes_unavailable"
    assert payload["state_changed"] is False


def test_hermes_rpg_plan_request_rejects_malformed_response() -> None:
    payload = request_hermes_rpg_plan({}, client=FakePlanClient({"command": ""}), enabled=True)

    assert payload["ok"] is False
    assert payload["error"] == "empty_command"
    assert payload["state_changed"] is False


def test_hermes_rpg_validator_accepts_service_command_in_service() -> None:
    payload = validate_hermes_rpg_proposal(
        {"state_flags": {"in_service": True}, "player": {"currency": {"silver": 5}}},
        {"proposal": {"command": "buy two rations"}},
    )

    assert payload["ok"] is True
    assert payload["valid"] is True
    assert payload["command"] == "buy two rations"
    assert payload["state_changed"] is False


def test_hermes_rpg_validator_rejects_service_without_service_state() -> None:
    payload = validate_hermes_rpg_proposal(
        {"state_flags": {"in_service": False}, "player": {"currency": {"silver": 5}}},
        {"proposal": {"command": "buy two rations"}},
    )

    assert payload["ok"] is False
    assert payload["error"] == "service_unavailable"
    assert payload["state_changed"] is False


def test_hermes_rpg_validator_rejects_combat_command_outside_combat() -> None:
    payload = validate_hermes_rpg_proposal(
        {"state_flags": {"in_combat": False}},
        {"proposal": {"command": "attack the bandit"}},
    )

    assert payload["ok"] is False
    assert payload["error"] == "combat_unavailable"


def test_hermes_rpg_validator_rejects_travel_during_combat() -> None:
    payload = validate_hermes_rpg_proposal(
        {"state_flags": {"in_combat": True}},
        {"proposal": {"command": "travel north"}},
    )

    assert payload["ok"] is False
    assert payload["error"] == "travel_blocked_by_combat"


def test_hermes_rpg_validator_rejects_missing_objective() -> None:
    payload = validate_hermes_rpg_proposal(
        {"state_flags": {}, "objectives": []},
        {"proposal": {"command": "focus on the objective"}},
    )

    assert payload["ok"] is False
    assert payload["error"] == "objective_unavailable"


def test_hermes_rpg_ticket_is_stable_and_not_ready() -> None:
    payload = {"ok": True, "plan": {"proposal": {"command": "check inventory"}}, "validation": {"valid": True}}

    first = hermes_rpg_ticket_payload(payload)
    second = hermes_rpg_ticket_payload(payload)

    assert first["ticket_id"] == second["ticket_id"]
    assert first["command"] == "check inventory"
    assert first["needs_user_step"] is True
    assert first["ready"] is False
    assert first["state_changed"] is False


def test_hermes_rpg_ticket_match_accepts_matching_valid_ticket() -> None:
    ticket = hermes_rpg_ticket_payload(
        {"ok": True, "plan": {"proposal": {"command": "check inventory"}}, "validation": {"valid": True}}
    )

    payload = hermes_rpg_ticket_match(ticket, ticket["ticket_id"])

    assert payload["ok"] is True
    assert payload["matched"] is True
    assert payload["command"] == "check inventory"
    assert payload["state_changed"] is False


def test_hermes_rpg_ticket_match_rejects_wrong_ticket() -> None:
    ticket = {"ticket_id": "abc", "command": "check inventory", "valid": True}

    payload = hermes_rpg_ticket_match(ticket, "different")

    assert payload["ok"] is False
    assert payload["error"] == "ticket_mismatch"
    assert payload["matched"] is False
    assert payload["state_changed"] is False


def test_hermes_rpg_plan_payload_returns_valid_review_plan() -> None:
    payload = hermes_rpg_plan_payload(
        {
            "session_id": "s1",
            "context_hash": "abc",
            "enabled": True,
            "context": {"state_flags": {}, "player": {}, "available_commands": ["check"]},
        },
        client=FakePlanClient({"command": "check inventory", "risk": "low"}),
    )

    assert payload["ok"] is True
    assert payload["mode"] == "review_required"
    assert payload["plan"]["proposal"]["command"] == "check inventory"
    assert payload["validation"]["valid"] is True
    assert payload["ticket"]["ready"] is False
    assert payload["state_changed"] is False


def test_hermes_plan_route_defaults_to_disabled_without_state_change() -> None:
    client = TestClient(create_gateway_app())
    response = client.post("/api/hermes/plan", json={"context": {"state_flags": {}}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == "hermes_disabled"
    assert payload["state_changed"] is False
