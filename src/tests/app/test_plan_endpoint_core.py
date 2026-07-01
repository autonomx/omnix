from __future__ import annotations

from typing import Any

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.plan_endpoint_core import plan_endpoint_payload


def test_plan_endpoint_payload_uses_injected_transport() -> None:
    calls: list[tuple[str, dict[str, Any], float]] = []

    def transport(url: str, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append((url, request, timeout))
        return {"ok": True, "status": "ok", "summary": "ready"}

    payload = plan_endpoint_payload(
        "  review next step  ",
        {"mode": "rpg"},
        transport=transport,
        config=HermesSidecarConfig(True, "http://local", 5),
    )

    assert calls == [("http://local/agent/plan", payload["request"], 5)]
    assert payload["request"]["objective"] == "review next step"
    assert payload["request"]["constraints"] == {
        "no_execution": True,
        "requires_review": True,
    }
    assert payload["sent"] is True
    assert payload["ok"] is True
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_plan_endpoint_payload_disabled_config_does_not_send() -> None:
    payload = plan_endpoint_payload(
        "review",
        {"mode": "rpg"},
        config=HermesSidecarConfig(False, "http://local", 5),
    )

    assert payload["sent"] is False
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_plan_endpoint_payload_disabled_config_returns_safe_status() -> None:
    payload = plan_endpoint_payload(
        "  review  ",
        {},
        config=HermesSidecarConfig(False, "http://local", 5),
    )

    assert payload["ok"] is False
    assert payload["status"] == "disabled"
    assert payload["sent"] is False
    assert payload["request"] == {
        "mode": "agent_mode",
        "objective": "review",
        "context": {},
        "constraints": {
            "no_execution": True,
            "requires_review": True,
        },
    }
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_plan_endpoint_payload_rejects_blank_objective_safely() -> None:
    payload = plan_endpoint_payload("   ", {"mode": "rpg"})

    assert payload["ok"] is False
    assert payload["status"] == "invalid_request"
    assert payload["sent"] is False
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_plan_endpoint_payload_rejects_missing_context_safely() -> None:
    payload = plan_endpoint_payload("review", None)

    assert payload["ok"] is False
    assert payload["status"] == "invalid_request"
    assert payload["sent"] is False
    assert payload["request"]["objective"] == "review"
    assert payload["request"]["context"] == {}
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
