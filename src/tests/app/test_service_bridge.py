from __future__ import annotations

from typing import Any

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.service_bridge import service_bridge_payload


def test_service_bridge_is_read_only() -> None:
    config = HermesSidecarConfig(False, "http://local", 5)
    payload = service_bridge_payload({}, config=config)

    assert payload["read_only"] is True
    assert payload["executes"] is False
    assert payload["sent"] is False


def test_service_bridge_success_path_uses_injected_transport() -> None:
    calls: list[tuple[str, dict[str, Any], float]] = []

    def transport(url: str, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append((url, request, timeout))
        return {"ok": True, "status": "ok", "proposal": {"summary": "ready"}}

    request = {"objective": "review", "context": {"mode": "rpg"}}
    config = HermesSidecarConfig(True, "http://local", 5)
    payload = service_bridge_payload(request, transport=transport, config=config)

    assert calls == [("http://local/agent/plan", request, 5)]
    assert payload["ok"] is True
    assert payload["sent"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
    assert payload["source"] == "service_bridge"
    assert payload["response"]["proposal"] == {"summary": "ready"}


def test_service_bridge_not_ok_transport_stays_non_executing() -> None:
    def transport(url: str, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        assert url == "http://local/agent/plan"
        assert request == {"objective": "review"}
        assert timeout == 5
        return {"ok": False, "status": "unavailable", "detail": "offline"}

    config = HermesSidecarConfig(True, "http://local", 5)
    payload = service_bridge_payload(
        {"objective": "review"},
        transport=transport,
        config=config,
    )

    assert payload["ok"] is False
    assert payload["status"] == "unavailable"
    assert payload["sent"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
    assert payload["response"]["detail"] == "offline"
