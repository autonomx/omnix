from __future__ import annotations

from typing import Any

from app.assist_core.hermes_rpg_plan_request import request_hermes_rpg_plan


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
