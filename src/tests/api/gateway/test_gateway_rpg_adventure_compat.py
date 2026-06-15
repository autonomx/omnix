"""RPG adventure-builder compatibility routes exposed through the gateway."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), raise_server_exceptions=False)


def test_gateway_rpg_adventure_templates_returns_legacy_envelope() -> None:
    response = _client().get("/api/rpg/adventure/templates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["templates"], list)


def test_gateway_rpg_adventure_validate_returns_validation_contract() -> None:
    response = _client().post("/api/rpg/adventure/validate", json={})

    assert response.status_code == 200
    payload = response.json()
    assert "ok" in payload
    assert "validation" in payload
    assert isinstance(payload["errors"], list)


def test_gateway_rpg_adventure_preview_returns_json_contract() -> None:
    response = _client().post("/api/rpg/adventure/preview", json={"setup": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "adventure_preview" in payload


def test_gateway_rpg_adventure_inspect_world_returns_inspector_contract() -> None:
    response = _client().post("/api/rpg/adventure/inspect-world", json={"setup": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "graph" in payload
    assert "simulation" in payload
    assert "inspector" in payload


def test_gateway_rpg_adventure_inspect_world_snapshot_returns_snapshot() -> None:
    response = _client().post(
        "/api/rpg/adventure/inspect-world-snapshot",
        json={"setup": {}, "label": "Gateway"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "snapshot" in payload


def test_gateway_rpg_adventure_compare_world_returns_diff() -> None:
    response = _client().post(
        "/api/rpg/adventure/compare-world",
        json={"before_setup": {}, "after_setup": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "diff" in payload


def test_gateway_rpg_adventure_compare_entity_requires_entity_id() -> None:
    response = _client().post(
        "/api/rpg/adventure/compare-entity",
        json={"before_setup": {}, "after_setup": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"success": False, "error": "Missing entity_id"}


def test_gateway_rpg_adventure_simulate_step_returns_updated_setup() -> None:
    response = _client().post("/api/rpg/adventure/simulate-step", json={"setup": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "updated_setup" in payload
    assert "simulation_state" in payload


def test_gateway_rpg_adventure_simulation_state_returns_state() -> None:
    response = _client().post("/api/rpg/adventure/simulation-state", json={"setup": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "simulation_state" in payload
