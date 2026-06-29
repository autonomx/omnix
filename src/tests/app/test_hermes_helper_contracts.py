from __future__ import annotations

from app.assist_core.hermes_contract import normalize_hermes_response, tool_calls_from_hermes
from app.assist_core.hermes_diagnostics import hermes_diagnostics_schema, hermes_diagnostics_status_payload
from app.assist_core.hermes_readouts import readout_payload
from app.assist_core.hermes_status import hermes_status_payload


def test_hermes_status_payload_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("HERMES_ENABLED", raising=False)
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("HERMES_API_KEY", raising=False)

    payload = hermes_status_payload()

    assert payload["enabled"] is False
    assert payload["reachable"] is False
    assert payload["state"] == "disabled"
    assert payload["base_url"] == "http://127.0.0.1:8642"


def test_hermes_diagnostics_status_includes_safe_route_contract(monkeypatch) -> None:
    monkeypatch.delenv("HERMES_ENABLED", raising=False)

    payload = hermes_diagnostics_status_payload()

    assert payload["diagnostics"]["status_path"] == "/api/hermes/status"
    assert payload["diagnostics"]["test_path"] == "/api/hermes/test"
    assert payload["diagnostics"]["test_dry_run_only"] is True
    assert payload["timeout_seconds"] >= 1.0


def test_hermes_contract_normalizes_actions_to_tool_calls() -> None:
    response = normalize_hermes_response(
        {
            "state": "accepted",
            "response": "I found a safe readout.",
            "domain": "house",
            "requires_review": True,
            "actions": [
                {
                    "tool": "get_house_status",
                    "args": {"scope": "summary"},
                    "risk": "low",
                    "reason": "Read-only status check.",
                }
            ],
            "trace": {"source": "test"},
        },
        fallback_domain="chat",
    )

    calls = tool_calls_from_hermes(response)

    assert response.state == "accepted"
    assert response.domain == "house"
    assert response.requires_review is True
    assert calls[0].name == "get_house_status"
    assert calls[0].args == {"scope": "summary"}


def test_hermes_contract_rejects_invalid_response() -> None:
    response = normalize_hermes_response("not a mapping")  # type: ignore[arg-type]

    assert response.state == "rejected"
    assert response.error == "invalid_response"
    assert response.actions == []


def test_unknown_readout_is_rejected_without_payload() -> None:
    payload = readout_payload("unknown")

    assert payload == {"ok": False, "name": "unknown", "error": "unknown_readout"}


def test_hermes_schema_marks_diagnostics_as_dry_run_only() -> None:
    schema = hermes_diagnostics_schema()

    assert schema["test"]["dry_run_only"] is True
    assert schema["assistant_request_contract"]["dry_run"] is True
