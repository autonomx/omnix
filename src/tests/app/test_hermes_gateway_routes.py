from __future__ import annotations

from tests.support.routers import effective_routes

from app.composition.gateway.main import create_gateway_app


HERMES_HIDDEN_ROUTES = {
    "/api/hermes/status",
    "/api/hermes/test",
    "/api/hermes/recent",
    "/api/hermes/adapter/preview",
    "/api/hermes/candidate/demo",
    "/api/hermes/rpg/context",
    "/api/hermes/rpg/suggestions",
    "/api/hermes/rpg/turn-readout",
    "/api/hermes/plan",
    "/api/hermes/approve",
}


def test_hermes_gateway_routes_are_registered() -> None:
    app = create_gateway_app()
    paths = {route.path for route in effective_routes(app)}

    assert HERMES_HIDDEN_ROUTES.issubset(paths)



def test_hermes_status_reports_the_sidecar_and_its_configuration(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.platform.chat.assist import diagnostics as hermes_diagnostics

    monkeypatch.setattr(hermes_diagnostics, "hermes_status_payload", lambda: {
        "enabled": True, "reachable": True, "state": "ready", "message": "Hermes is reachable.",
        "base_url": "http://127.0.0.1:8642", "health": {"ok": True}, "capabilities": {}, "error": None,
    })
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1:8000", headers={"X-Omnix-Client": "test"})

    payload = client.get("/api/hermes/status").json()

    assert payload["reachable"] is True and payload["state"] == "ready"
    assert payload["diagnostics"] == {"status_path": "/api/hermes/status", "test_path": "/api/hermes/test", "test_dry_run_only": True}
    assert isinstance(payload["timeout_seconds"], float) and isinstance(payload["api_key_configured"], bool)
